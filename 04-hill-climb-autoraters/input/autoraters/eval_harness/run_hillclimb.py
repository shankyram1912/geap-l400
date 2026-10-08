"""Hill Climbing Execution & Evaluation Harness.

Runs target edge-case properties through the ADK agent, evaluates them on
key noisy criteria ('cost-per-acre' and 'neighboring-flood-risk') using
the GenAI Evaluation Service with k=1, and computes their mean scores.
Automatically versions execution folders under runs/hillclimb_X/.
"""

import argparse
import json
import os
import re
import sys
import numpy as np

# Disable Mutual TLS (mTLS) for concurrent safety in Vertex SDK
os.environ["GOOGLE_API_USE_MTLS"] = "never"
os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

from eval_harness.create_re_agent_evalset import build_real_estate_evalset
from eval_harness.run_geap_eval import GeapEvalRunner


def get_next_run_dir(runs_dir: str, base_name: str) -> str:
    """Finds the next available versioned directory suffix (e.g. base_name_X)."""
    if not os.path.exists(runs_dir):
        os.makedirs(runs_dir, exist_ok=True)
        return os.path.join(runs_dir, f"{base_name}_1")

    subdirs = os.listdir(runs_dir)
    max_idx = 0
    for d in subdirs:
        match = re.match(rf"^{re.escape(base_name)}_(\d+)$", d)
        if match:
            max_idx = max(max_idx, int(match.group(1)))

    return os.path.join(runs_dir, f"{base_name}_{max_idx + 1}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hill Climbing Harness: Run agent and evaluate key criteria."
    )
    parser.add_argument(
        "--lots-file",
        default="eval_harness/hillclimb_lots.txt",
        help="Path to the file containing target lot IDs (default: eval_harness/hillclimb_lots.txt)",
    )
    parser.add_argument(
        "--rubrics-file",
        default="eval_harness/rubrics.json",
        help="Path to the rubric definitions JSON (default: eval_harness/rubrics.json)",
    )
    parser.add_argument(
        "--agent-dir",
        default="re_analyst",
        help="Path to the ADK agent directory (default: re_analyst)",
    )
    parser.add_argument(
        "--runs-dir",
        default="runs",
        help="Directory to store versioned run folders (default: runs)",
    )

    parser.add_argument(
        "--evalset-dir",
        default=None,
        help="Directory where the generated evalset JSON will be written (default: same as --agent-dir)",
    )
    parser.add_argument(
        "--qps",
        type=float,
        default=None,
        help="Optional QPS throttle limit for the evaluation service",
    )

    args = parser.parse_args()

    # Verify files exist.
    if not os.path.exists(args.lots_file):
        print(f"❌ Error: Lots file not found at {args.lots_file}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.rubrics_file):
        print(f"❌ Error: Rubrics file not found at {args.rubrics_file}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.agent_dir):
        print(f"❌ Error: Agent directory not found at {args.agent_dir}", file=sys.stderr)
        sys.exit(1)

    # Load Lot IDs
    with open(args.lots_file, "r", encoding="utf-8") as f:
        lot_ids = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    if not lot_ids:
        print(f"❌ Error: No valid Lot IDs found in {args.lots_file}", file=sys.stderr)
        sys.exit(1)

    # Determine target versioned directory.
    runs_dir = os.path.abspath(args.runs_dir)
    run_dir = get_next_run_dir(runs_dir, "hillclimb")
    print(f"📂 Created versioned run directory: {run_dir}")
    run_name = os.path.basename(run_dir)

    # Path for ADK EvalSet.
    evalset_dir = args.evalset_dir if args.evalset_dir is not None else args.agent_dir
    evalset_path = os.path.abspath(os.path.join(evalset_dir, f"{run_name}.evalset.json"))

    # Generate agent traces.
    print(f"\n🤖 Running agent '{args.agent_dir}' over target lots to generate traces...")
    build_real_estate_evalset(
        lot_ids=lot_ids,
        output_path=evalset_path,
        eval_set_id=run_name,
        agent_dir=args.agent_dir,
    )

    # Run GenAI Evaluation Service for k=1.
    target_criteria = ["cost-per-acre", "neighboring-flood-risk"]
    
    geap_runner = GeapEvalRunner(
        traces_path=evalset_path,
        rubric_file_path=args.rubrics_file,
        judge_model_sampling_count=1,
        evaluation_service_qps=args.qps,
        target_criterion_ids=target_criteria,
    )

    print(f"\n☁️ Dispatching single-pass (k=1) evaluation for criteria: {target_criteria}...")
    geap_runner.execute_cloud_evaluation(
        k_passes=1,
        experiment_name="hillclimb",
    )

    output_json_path = os.path.join(run_dir, f"geap_calls_and_responses_{run_name}.json")
    saved_file = geap_runner.assemble_and_save_records(output_json_path)
    print(f"✅ Evaluation results saved to -> {saved_file}")

    # Compute mean score for each criteria..
    with open(saved_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    means = {}
    for crit_id in target_criteria:
        scores = []
        for r in records:
            if r["criterion_id"] == crit_id:
                for resp in r.get("responses_from_service", []):
                    val = resp.get("score")
                    if val is not None:
                        scores.append(float(val))
        means[crit_id] = np.mean(scores) if scores else float("nan")

    print("\n=========================================")
    print(f"📊 Hill Climbing Results: {run_name}")
    print("=========================================")
    for crit_id in target_criteria:
        mean_val = means[crit_id]
        mean_str = f"{mean_val:.4f}" if not np.isnan(mean_val) else "N/A"
        print(f" • {crit_id:<25} Mean Score: {mean_str}")
    print("=========================================\n")


if __name__ == "__main__":
    main()
