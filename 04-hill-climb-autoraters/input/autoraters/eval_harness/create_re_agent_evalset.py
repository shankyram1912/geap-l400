"""Real Estate Investment Opportunity Analysis Agent: Evaluation Dataset Builder.

Specifically tailored for the Autorater Lab, this utility takes a text file containing
target property Lot IDs (one per line) and generates an ADK EvalSet JSON file
formatted with the required investment suitability evaluation prompts and conversation plans.
"""

import argparse
import asyncio
import importlib
import json
import os
import sys
from typing import List, Optional

from google.adk.evaluation.eval_case import ConversationScenario, EvalCase
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.evaluation_generator import EvaluationGenerator
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from eval_harness.utils import load_app_from_dir

_load_app_from_dir = load_app_from_dir


def build_real_estate_evalset(
    lot_ids: List[str],
    output_path: str,
    eval_set_id: str = None,
    agent_dir: Optional[str] = None,
    max_concurrency: int = 10,
) -> str:
    """Constructs an ADK EvalSet JSON file specifically for the real estate evaluation task.

    Takes a list of target property Lot IDs, formats each into a standardized
    investment suitability evaluation prompt and conversation plan, executes the
    target ADK agent concurrently over them (if agent_dir is provided, bounded by
    max_concurrency), and dumps the resulting Pydantic EvalSet model to disk in
    ADK 2.0 schema format.

    Args:
        lot_ids: A list of property identification strings (e.g., ['LOT-8472', 'LOT-8471']).
        output_path: Absolute or relative file path where the generated .evalset.json file
          will be saved.
        eval_set_id: Optional unique identifier for the EvalSet. If omitted, it is automatically derived
          from the base filename of output_path.
        agent_dir: Optional path to the ADK agent directory (e.g., './re_analyst'). If provided,
          executes the agent to populate conversation telemetry.
        max_concurrency: Maximum number of property evaluations to execute concurrently when
          agent_dir is provided (default: 10).

    Returns:
        The file path where the generated EvalSet JSON was saved.

    Raises:
        ValueError: If lot_ids is empty or contains no valid non-comment property IDs.
    """
    if not lot_ids:
        raise ValueError("No lot IDs provided in the input file.")

    if not eval_set_id:
        base_name = os.path.basename(output_path)
        eval_set_id = base_name.replace(".evalset.json", "").replace(".json", "")

    cases = []
    for lot_id in lot_ids:
        # Explicit prompt and plan templates for real estate investment suitability evaluation
        prompt = f"Please evaluate investment suitability for lot {lot_id} and generate a report."
        plan = f"User requests initial site evaluation memorandum for lot {lot_id}."

        case = EvalCase(
            eval_id=lot_id,
            conversation_scenario=ConversationScenario(
                starting_prompt=prompt,
                conversation_plan=plan,
            ),
        )
        cases.append(case)

    # If agent_dir is provided and exists, run the agent over the cases to populate telemetry natively
    if agent_dir and os.path.exists(agent_dir):
        try:
            app = _load_app_from_dir(agent_dir)
            session_service = InMemorySessionService()
            runner = Runner(
                app=app, session_service=session_service, auto_create_session=True
            )

            print(
                f"\n🚀 Executing '{app.name}' over {len(cases)} properties to populate evaluation traces..."
            )
            print("-" * 65)

            print(
                f"⚡ Starting concurrent execution across {len(cases)} properties (max concurrency: {max_concurrency})...",
                flush=True,
            )

            semaphore = asyncio.Semaphore(max_concurrency)

            async def _run_single_case(i: int, case: EvalCase):
                async with semaphore:
                    try:
                        prompt = case.conversation_scenario.starting_prompt
                        session_id = f"session_{eval_set_id}_{case.eval_id}"
                        async for _ in runner.run_async(
                            user_id="learner",
                            session_id=session_id,
                            new_message=types.Content(
                                role="user", parts=[types.Part.from_text(text=prompt)]
                            ),
                        ):
                            pass
                        session = await session_service.get_session(
                            app_name=app.name, user_id="learner", session_id=session_id
                        )
                        if session and session.events:
                            case.conversation = (
                                EvaluationGenerator.convert_events_to_eval_invocations(
                                    session.events
                                )
                            )
                            case.conversation_scenario = None
                        print(
                            f"✅ [{i+1}/{len(cases)}] Completed trace for {case.eval_id}",
                            flush=True,
                        )
                    except Exception as e:
                        print(
                            f"⚠️ [{i+1}/{len(cases)}] Failed trace for {case.eval_id}: {e}",
                            file=sys.stderr,
                            flush=True,
                        )

            async def _run_all_cases():
                await asyncio.gather(
                    *[_run_single_case(i, case) for i, case in enumerate(cases)]
                )
                print(f"\nCleaning up resources...")
                await runner.close()
                # Below is cleanup for ADK's model client, which 
                #   has its own async pool for model API calls.
                if hasattr(app.root_agent, "model") and hasattr(
                    app.root_agent.model, "api_client"
                ):
                    client = app.root_agent.model.api_client
                    if hasattr(client, "aio") and hasattr(client.aio, "aclose"):
                        await client.aio.aclose()
                    if hasattr(client, "close"):
                        client.close()
                await asyncio.sleep(0.25)

            asyncio.run(_run_all_cases())
        except Exception as e:
            print(f"\n⚠️ Note: Could not execute agent in '{agent_dir}' ({e}). Saving unpopulated prompts only.", file=sys.stderr)

    eval_set = EvalSet(
        eval_set_id=eval_set_id,
        name=f"Real Estate Evaluation Dataset ({len(cases)} properties)",
        description=(
            f"Investment suitability evaluation dataset for properties: "
            f"{', '.join([c.eval_id for c in cases[:5]])}"
        ),
        eval_cases=cases,
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(eval_set.model_dump_json(indent=2, by_alias=True))

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Autorater Lab Dataset Builder: Generates an ADK EvalSet JSON file from a text "
            "file of target property Lot IDs for real estate investment opportunity analysis agent evaluation."
        )
    )
    parser.add_argument(
        "--lots-file",
        required=True,
        help="Path to a text file containing target lot IDs (one per line)",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output path for the generated ADK EvalSet JSON",
    )
    parser.add_argument(
        "--eval-set-id",
        help="Optional ID for the EvalSet (default: derived from output filename)",
    )
    parser.add_argument(
        "--agent-dir",
        default="./re_analyst",
        help="Path to the ADK agent directory to execute over the dataset (default: ./re_analyst)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.lots_file):
        print(f"❌ Error: Lots file not found at {args.lots_file}", file=sys.stderr)
        sys.exit(1)

    with open(args.lots_file, "r", encoding="utf-8") as f:
        lot_ids = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    try:
        out_file = build_real_estate_evalset(
            lot_ids=lot_ids,
            output_path=args.out,
            eval_set_id=args.eval_set_id,
            agent_dir=args.agent_dir,
        )
        print(
            f"✅ Successfully generated real estate evaluation dataset for {len(lot_ids)} properties -> {out_file}"
        )
    except Exception as e:
        print(f"❌ Error building real estate EvalSet: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
