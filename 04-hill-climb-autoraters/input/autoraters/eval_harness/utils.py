"""Utility functions for Autorater Lab Evaluation Harness."""

import importlib
import json
import os
import sys
from typing import Any, Dict, List, Tuple, Union
from google.adk.apps import App
import numpy as np
import pandas as pd


def format_val(val: Any, fmt: str, default: str = "N/A") -> str:
    """Formats a numeric value using the given format string, handling NaNs."""
    if pd.isna(val):
        return default
    try:
        return fmt.format(val)
    except (ValueError, TypeError):
        return default


def load_eval_ratings_by_criterion(eval_output_path: str) -> Dict[str, Dict[str, Any]]:
    """Loads a GEAP evaluation output file and groups flat rating records by criterion.

    Args:
        eval_output_path: Path to the JSON evaluation output file from run_geap_eval.py.

    Returns:
        A dictionary mapping criterion_id to its name and list of rating records:
            {
                "environmental-esa": {
                    "name": "Environmental Status (Phase I ESA) Evaluation",
                    "ratings": [
                        {
                            "eval_id": "LOT-1000",
                            "pass_idx": "pass-1",
                            "score": 5.0,
                            "explanation": "..."
                        },
                        ...
                    ]
                }
            }

    Raises:
        FileNotFoundError: If the evaluation output file does not exist at the specified path.
        ValueError: If the evaluation output file is empty.
    """
    if not os.path.exists(eval_output_path):
        raise FileNotFoundError(f"Evaluation output file not found at {eval_output_path}")

    with open(eval_output_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not records:
        raise ValueError(f"Evaluation output file {eval_output_path} is empty.")

    # Check if the collection is a dry-run
    if any(r.get("is_dry_run") for r in records):
        print(
            f"ℹ️ Evaluation output file {eval_output_path} was generated in dry-run mode. "
            "Statistical analysis is not supported for dry runs.",
            file=sys.stderr,
        )
        sys.exit(0)

    structured_data = {}
    for r in records:
        eval_id = r["eval_id"]
        criterion_id = r["criterion_id"]
        criterion_name = r["criterion_name"]
        
        if criterion_id not in structured_data:
            structured_data[criterion_id] = {
                "name": criterion_name,
                "ratings": []
            }
            
        for resp in r.get("responses_from_service", []):
            pass_idx = int(resp["eval_pass_index"])
            score = resp["score"]
            explanation = resp.get("explanation", "No explanation returned by the GEAP evaluation service.")
            structured_data[criterion_id]["ratings"].append({
                "eval_id": eval_id,
                "pass_idx": f"pass-{pass_idx}",
                "score": float(score) if score is not None else np.nan,
                "explanation": explanation
            })
    return structured_data


def build_grades_dataframe(flat_data: Union[List[Dict[str, Any]], pd.DataFrame]) -> pd.DataFrame:
    """Builds a structured pivoted DataFrame of scores from flattened records.

    Args:
        flat_data: List of flattened dicts or a pre-built flat DataFrame.

    Returns:
        A DataFrame with eval_id as the index and sorted, renamed pass columns (e.g., 'p1', 'p2', ...) based on pass_idx.
    """
    df = pd.DataFrame(flat_data) if isinstance(flat_data, list) else flat_data.copy()
    grades_df = df.pivot(index="eval_id", columns="pass_idx", values="score")
    grades_df = grades_df.rename(columns=lambda x: x.replace("pass-", "p"))
    grades_df = grades_df[sorted(grades_df.columns, key=lambda x: int(x[1:]))]
    return grades_df


def load_app_from_dir(agent_dir: str) -> App:
    """Dynamically imports and returns the ADK App instance from a local agent directory.

    Resolves the absolute path of the target directory, temporarily adds its parent
    directory to sys.path during import to enable module and submodule resolution,
    and removes it immediately after loading so sys.path is not permanently modified.

    Args:
        agent_dir: Path to the local ADK agent directory (e.g., './re_analyst').

    Returns:
        The google.adk.apps.App instance defined in the agent module.

    Raises:
        ImportError: If the agent module cannot be imported from the specified directory.
        AttributeError: If the imported module does not define an 'app' attribute.
    """
    abs_dir = os.path.abspath(agent_dir)
    parent_dir = os.path.dirname(abs_dir)
    mod_name = os.path.basename(abs_dir)

    path_inserted = False
    # Add parent directory of agent to sys.path to allow importing the agent module and
    # its submodules, but only if parent directory not already in sys.path.
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
        path_inserted = True

    try:
        mod = importlib.import_module(f"{mod_name}.agent")
    except ImportError as e:
        raise ImportError(
            f"Failed to import agent module from {abs_dir}/agent.py: {e}"
        )
    finally:
        # Remove parent directory from sys.path to avoid side effects.
        if path_inserted and parent_dir in sys.path:
            sys.path.remove(parent_dir)

    if not hasattr(mod, "app"):
        raise AttributeError(f"Module {abs_dir}/agent.py does not define 'app'.")
    return mod.app
