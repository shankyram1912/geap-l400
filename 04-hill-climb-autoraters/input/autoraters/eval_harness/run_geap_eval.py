"""Autorater Lab GEAP Evaluation Runner.

This script acts as the automated bridge between ADK evaluation traces and Vertex AI's
GenAI Evaluation Service (GEAP). It parses generated property analysis reports, loads
rubrics to evaluate the reports, dispatches cloud evaluations (or simulates dry runs)
based on the rubrics to evaluate the reports, and assembles the exact evaluation prompts
and responses for downstream statistical analysis.

Pedagogical Core Flow:
  1. Extract property responses from ADK EvalSet JSON traces.
  2. Load evaluation rubrics from a local JSON file.
  3. Compile evaluation prompts using the Vertex AI SDK's template engine.
  4. Dispatch evaluation calls to the cloud service (k-passes).
  5. Assemble the final prompts on-the-fly and save the evaluation prompts and responses.
"""

import argparse
from collections import defaultdict
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Disable Mutual TLS (mTLS) to bypass pyOpenSSL backend injection. This prevents the
# "Context has already been used to create a Connection" error triggered by pyOpenSSL
# when EvalTask executes concurrent evaluations.
os.environ["GOOGLE_API_USE_MTLS"] = "never"
os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

import pandas as pd
import vertexai
from vertexai.evaluation import EvalTask, PointwiseMetric, PointwiseMetricPromptTemplate


class GeapEvalRunner:
    """Orchestrates GenAI Evaluation Service (GEAP) calls for ADK evaluation traces."""

    def __init__(
        self,
        traces_path: str,
        rubric_file_path: str,
        judge_model_sampling_count: int = 1,
        evaluation_service_qps: Optional[float] = None,
        target_criterion_ids: Optional[List[str]] = None,
    ):
        """Initializes the evaluation runner by loading traces and criteria.

        Args:
            traces_path: Path to the ADK EvalSet JSON file containing agent runs.
            rubric_file_path: Path to the rubric JSON file defining all criteria.
            judge_model_sampling_count: Number of times the judge model samples responses.
            evaluation_service_qps: QPS throttle limit for the evaluation service.
            target_criterion_ids: Optional list of criterion IDs to evaluate (filters all criteria).
        """
        self.traces = self._load_traces(traces_path)
        self.criteria = self._load_criteria(rubric_file_path)
        if target_criterion_ids is not None:
            self.criteria = [c for c in self.criteria if c["rubric_id"] in target_criterion_ids]
        self.judge_model_sampling_count = judge_model_sampling_count
        self.evaluation_service_qps = evaluation_service_qps
        self.pointwise_metrics = self._build_pointwise_metrics()
        self.evaluation_results: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

    def _load_traces(self, traces_path: str) -> List[Dict[str, str]]:
        """Reads an ADK EvalSet JSON file and extracts a list of {'eval_id': ..., 'response': ...}.

        Args:
            traces_path: Path to the ADK EvalSet JSON file containing agent runs.

        Returns:
            List[Dict[str, str]]: A list of trace dictionaries, where each dictionary
              contains 'eval_id' (the case ID) and 'response' (the final generated output text).
        """
        if not os.path.exists(traces_path):
            raise FileNotFoundError(f"EvalSet traces file not found at {traces_path}")

        with open(traces_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = []
        # In ADK, each run trace is stored as an 'eval_case' inside 'eval_cases'.
        for case in data["eval_cases"]:
            eval_id = str(case["evalId"])
            try:
                # The final generated response is nested inside the conversation history's last message.
                response = case["conversation"][-1]["finalResponse"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError) as e:
                print(
                    f"⚠️ Warning: Expected finalResponse text for case '{eval_id}' in {traces_path}, "
                    f"but extraction failed ({e}). Skipping this case from evaluation.",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            records.append({
                "eval_id": eval_id,
                "response": response,
            })

        return records

    def _load_criteria(self, rubric_file_path: str) -> List[Dict[str, Any]]:
        """Loads evaluation criteria from a JSON file and transforms them to match GEAP's expected format.

        The Gen AI Evaluation Service (GEAP) PointwiseMetricPromptTemplate expects:
          - 'criteria': A dictionary mapping the criterion name to its descriptive evaluation rules.
          - 'rating_rubric': A dictionary mapping rating levels ('1' through '5') to scoring descriptions.

        This function maps our lab's rubrics.json fields ('criterion' and 'rating_scale') directly into this
        expected GEAP structure so they can be unpacked cleanly into PointwiseMetricPromptTemplate.

        Args:
            rubric_file_path: Path to the rubric JSON file.

        Returns:
            List[Dict[str, Any]]: A list of normalized criteria dictionaries containing 'rubric_id',
              'name', 'criteria', and 'rating_rubric'.
        """
        if not os.path.exists(rubric_file_path):
            raise FileNotFoundError(f"Rubric file not found at {rubric_file_path}")

        with open(rubric_file_path, "r", encoding="utf-8") as f:
            criteria_definitions = json.load(f)

        geap_criteria = []
        for r in criteria_definitions:
            name = str(r["name"])
            geap_criteria.append({
                "rubric_id": str(r["criterion_id"]),              # mapped to SDK's expected 'rubric_id'
                "name": name,
                "criteria": {name: str(r["criterion"])},          # GEAP expects Dict[str, str] for criteria
                "rating_rubric": r["rating_scale"],               # GEAP expects 'rating_rubric' for rating scale
            })
        return geap_criteria

    def _build_pointwise_metrics(self) -> List[PointwiseMetric]:
        """Builds a list of PointwiseMetric objects for all criteria.
        See https://docs.cloud.google.com/python/docs/reference/vertexai/latest/vertexai.evaluation.PointwiseMetric

        For every criterion, we build:
          1. A PointwiseMetricPromptTemplate: Holds instructions, the criterion description and scale,
             and other information needed to evaluate the response. The GEAP Gen AI eval service
             requires this template as one of the inputs to do evaluation, along with the response.
          2. A PointwiseMetric: Associates the template with a metric name (criterion_id/rubric_id), allowing the
             Vertex AI SDK to track the metric's evaluations and responses.

        Returns:
            List[PointwiseMetric]: PointwiseMetric objects for EvalTask.
        """
        pointwise_metrics = []

        for r in self.criteria:
            # Step 1: Instantiate the prompt template with our criteria and rating scale.
            template = PointwiseMetricPromptTemplate(
                criteria=r["criteria"],
                rating_rubric=r["rating_rubric"],
                input_variables=["response"],  # Instructs GEAP genai eval to map 'response' into the prompt template
            )
            
            # SDK WORKAROUND: There is a bug in the Vertex AI SDK's _MetricPromptTemplate class where it
            # inherits from PromptTemplate but fails to invoke super().__init__(). This leaves the internal
            # 'variables' property uninitialized. We manually call _get_variables() to populate it so that
            # the template's .assemble() method works correctly later during on-the-fly rendering.
            template.variables = template._get_variables()

            # Step 2: Wrap the template inside a PointwiseMetric object that the EvalTask can execute.
            # We use the criterion_id directly as the metric name so that the results table columns
            # map directly to our criterion IDs without any translation.
            metric = PointwiseMetric(
                metric=r["rubric_id"],
                metric_prompt_template=template,
            )
            if self.judge_model_sampling_count is not None:
                metric.judge_model_sampling_count = self.judge_model_sampling_count
            pointwise_metrics.append(metric)

        return pointwise_metrics

    def execute_cloud_evaluation(
        self,
        k_passes: int,
        experiment_name: Optional[str] = None,
        project: Optional[str] = None,
        location: str = "us-central1",
    ):
        """Runs k stochastic evaluation passes using Vertex AI GenAI Eval Service.

        This function coordinates the live cloud API execution:
          1. Converts our trace dataset to a Pandas DataFrame (required by the Vertex AI SDK).
          2. Instantiates `EvalTask` with the dataset, custom pointwise metrics, and experiment run group.
          3. Executes `eval_task.evaluate()` in a loop k times.
          4. Parses each pass's tabular results.

        Args:
            k_passes: Number of times to run the eval for each trace+pointwise_metric.
            experiment_name: Experiment name for logging runs in Cloud Console.
            project: Google Cloud project ID, otherwise will use environment variable GOOGLE_CLOUD_PROJECT.
            location: Google Cloud region for Vertex AI.
        """
        try:
            if project:
                vertexai.init(project=project, location=location)
            else:
                vertexai.init(location=location)
        except Exception as e:
            print(f"⚠️ Vertex AI initialization failed ({e}). Falling back to dry-run mode.", file=sys.stderr)
            return

        if experiment_name:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            experiment_name = f"{experiment_name}-{timestamp}"
            print(f"🧪 Vertex AI Experiment Name: {experiment_name}")

        # Convert traces to a Pandas DataFrame containing only the 'response' column.
        # The Vertex AI SDK requires a DataFrame (or local CSV path) to hold the responses
        # that will be evaluated.
        dataset_df = pd.DataFrame(self.traces)[["response"]]

        # Run evaluations k times to allow for variance tracking.
        for eval_pass_idx in range(1, k_passes + 1):
            print(f"  ☁️ Dispatching EvalTask pass {eval_pass_idx}/{k_passes} to Vertex AI...")
            try:
                # Instantiate a clean EvalTask for this pass to avoid "Context has already been used to create a Connection" SSL error.
                eval_task = EvalTask(
                    dataset=dataset_df,
                    metrics=self.pointwise_metrics,
                    experiment=experiment_name,
                )
                # Execute the cloud evaluation pass
                eval_result = eval_task.evaluate(
                    experiment_run_name=f"pass-{eval_pass_idx}" if experiment_name else None,
                    evaluation_service_qps=self.evaluation_service_qps,
                )
                
                # The SDK returns results in a pandas DataFrame: eval_result.metrics_table.
                # Row index matches the input dataset order, while columns are named:
                # '{metric_name}/score' and '{metric_name}/explanation'
                metrics_table = eval_result.metrics_table

                # Parse out the score and explanation for each evaluation case and pointwise metric
                for idx, item in enumerate(self.traces):
                    eval_id = str(item["eval_id"])
                    for metric in self.pointwise_metrics:
                        criterion_id = metric.metric_name
                        score_col = f"{criterion_id}/score"
                        expl_col = f"{criterion_id}/explanation"

                        score = metrics_table.iloc[idx][score_col] if score_col in metrics_table.columns else None
                        expl = (
                            str(metrics_table.iloc[idx][expl_col])
                            if expl_col in metrics_table.columns
                            else "No explanation returned."
                        )

                        # Store results in the evaluation_results map, keyed by (eval_id, criterion_id).
                        # This allows us to look up results by combining the eval_id from the trace
                        # and the criterion_id from the pointwise metric.
                        self.evaluation_results[(eval_id, criterion_id)].append({
                            "eval_pass_index": eval_pass_idx,
                            "score": float(score) if pd.notnull(score) else None,
                            "explanation": expl,
                        })
            except Exception as e:
                print(f"  ⚠️ Live Cloud evaluation pass {eval_pass_idx} failed: {e}", file=sys.stderr)

    def assemble_and_save_records(self, output_path: str) -> str:
        """Renders the final prompts on-the-fly and saves the collection to a JSON file.

        This function loops over every trace and criterion. For each combination:
          1. Renders the prompt sent to the GEAP genai eval service using the template's
             .assemble(response=...) method.
          2. Couples it with the list of k-pass evaluation responses (or sets an
             'is_dry_run' flag if the results map is empty).
          3. Appends the structured record to the final collection and writes it to disk.

        Args:
            output_path: File path to save the JSON of the eval prompts and autorater results.

        Returns:
            str: Absolute path of the saved JSON file.
        """
        final_collection_records = []
        is_dry_run = not bool(self.evaluation_results)

        # Map each criterion ID back to its corresponding PointwiseMetricPromptTemplate from the pointwise_metrics.
        # The PointwiseMetric object stores its raw template object in its '_raw_metric_prompt_template' attribute.
        criterion_id_to_prompt_template = {
            metric.metric_name: metric._raw_metric_prompt_template for metric in self.pointwise_metrics
        }

        for item in self.traces:
            eval_id = item["eval_id"]
            response_text = item["response"]

            for r in self.criteria:
                criterion_id = r["rubric_id"]                     # self.criteria normalized elements use rubric_id internally
                template = criterion_id_to_prompt_template[criterion_id]

                # Use the SDK's template.assemble method to get the fully populated prompt
                # by replacing the {response} variable with our actual report content.
                prompt_made = str(template.assemble(response=response_text))

                record = {
                    "eval_id": eval_id,
                    "criterion_id": criterion_id,
                    "criterion_name": r["name"],
                    "prompt_made_to_service": prompt_made,
                }
                if is_dry_run:
                    record["is_dry_run"] = True
                else:
                    record["responses_from_service"] = self.evaluation_results.get((eval_id, criterion_id), [])

                final_collection_records.append(record)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_collection_records, f, indent=2, ensure_ascii=False)

        return os.path.abspath(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Autorater Lab GEAP Evaluation Runner: Extracts traces, builds prompts, and runs cloud evaluations."
    )
    parser.add_argument(
        "--traces",
        required=True,
        help="Path to input ADK EvalSet JSON file (e.g., re_analyst/hillclimb_lots.evalset.json)",
    )
    parser.add_argument(
        "--rubric-file",
        default="eval_harness/rubrics.json",
        help="Path to the rubric JSON file defining all criteria (default: eval_harness/rubrics.json)",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output path for collected calls and responses JSON (e.g., runs/baseline/geap_calls_and_responses.json)",
    )
    parser.add_argument(
        "-k",
        "--k-passes",
        type=int,
        default=1,
        help="Number of stochastic evaluation passes to execute per property x criterion pair (default: 1)",
    )
    parser.add_argument(
        "--experiment-name",
        default="autorater-lab",
        help="Experiment grouping name for Vertex AI Console",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble prompts and save collection file without executing live cloud API calls",
    )
    parser.add_argument(
        "--project",
        help="Google Cloud project ID (optional, defaults to application-default)",
    )
    parser.add_argument(
        "--location",
        default="us-central1",
        help="Google Cloud location for Vertex AI (default: us-central1)",
    )
    parser.add_argument(
        "--judge-model-sampling-count",
        type=int,
        default=1,
        help="Number of times the judge model should sample a response for evaluation (1 to 32, default: 1)",
    )
    parser.add_argument(
        "--evaluation-service-qps",
        type=float,
        default=None,
        help="Rate limit (Queries Per Second) for dispatching evaluation requests (optional)",
    )

    args = parser.parse_args()

    try:
        # 1. Instantiate the evaluator runner
        runner = GeapEvalRunner(
            traces_path=args.traces,
            rubric_file_path=args.rubric_file,
            judge_model_sampling_count=args.judge_model_sampling_count,
            evaluation_service_qps=args.evaluation_service_qps,
        )

        # 2. Execute cloud evaluations if not running in dry-run mode
        if not args.dry_run:
            runner.execute_cloud_evaluation(
                k_passes=args.k_passes,
                experiment_name=args.experiment_name,
                project=args.project,
                location=args.location,
            )

        # 3. Assemble final prompts and save the JSON collection
        out_file = runner.assemble_and_save_records(output_path=args.out)
        print(f"\n✅ Successfully generated GEAP call collection file -> {out_file}")
        print(f"📊 Total records generated: {len(runner.traces) * len(runner.criteria)} ({len(runner.traces)} responses × {len(runner.criteria)} criteria, {args.k_passes} passes each)")
    except Exception as e:
        print(f"❌ Error assembling/executing GEAP calls: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
