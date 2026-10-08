"""Tool to print detailed textual explanations and rationales from LLM judge passes.

Supports filtering by Lot ID mean scores and individual pass scores.
"""

import argparse
import sys
from typing import Any, Dict, List
import pandas as pd

from eval_harness.utils import load_eval_ratings_by_criterion


def print_explanations(
    criterion_ratings: List[Dict[str, Any]],
    score_threshold: float,
) -> None:
    """Prints detailed rationale explanations per property and pass with filtering.

    Args:
        criterion_ratings: List of flat rating dicts as returend by utils.load_eval_ratings_by_criterion().
        score_threshold: Only show individual pass explanations with a score <= this value.
    """
    # Group by eval_id (Lot ID).
    from collections import defaultdict
    ratings_by_lot = defaultdict(list)
    for row in criterion_ratings:
        ratings_by_lot[row["eval_id"]].append(row)

    # Sort and iterate through Lot IDs and their ratings.
    for eval_id, rows in sorted(ratings_by_lot.items()):
        
        # Check if there are any valid scores for this Lot ID
        valid_scores = [r["score"] for r in rows if not pd.isna(r["score"])]
        if not valid_scores:
            continue

        print(f"\n--- Property ID: {eval_id} ---")
        
        sorted_passes = sorted(rows, key=lambda x: int(x["pass_idx"].split("-")[1]))
        
        for row in sorted_passes:
            p_label = row["pass_idx"].replace("pass-", "p")
            score = row["score"]
            explanation = row["explanation"]
            
            # Check if this pass matches the score filter
            show_pass_explanation = (not pd.isna(score) and score <= score_threshold)
            
            if show_pass_explanation:
                print(f"  [{p_label}] Score: {score}")
                print(f"  Rationale: {explanation}")
            else:
                # Still display the score, just not the explanation
                print(f"  [{p_label}] Score: {score}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print detailed LLM judge explanations with Lot and pass score filters."
    )
    parser.add_argument(
        "--run_geap_eval_out",
        required=True,
        help="Path to eval calls and responses output by run_geap_eval.py",
    )
    parser.add_argument(
        "--criterion",
        required=True,
        help="Criterion ID to analyze",
    )
    parser.add_argument(
        "--max_score_to_show",
        type=float,
        default=4.0,
        help="Only show individual eval pass explanations with a score equal to or below this value (default: 4.0)",
    )

    args = parser.parse_args()

    try:
        ratings_by_criterion = load_eval_ratings_by_criterion(args.run_geap_eval_out)
        
        if args.criterion not in ratings_by_criterion:
            print(f"❌ No records found for criterion ID: '{args.criterion}'", file=sys.stderr)
            sys.exit(1)

        criterion_info = ratings_by_criterion[args.criterion]
        criterion_name = criterion_info["name"]
        criterion_ratings = criterion_info["ratings"]

        print(f"=========================================")
        print(f"🔍 Criterion ID: {args.criterion}")
        print(f"📋 Name:         {criterion_name}")
        print(f"=========================================")
        print(f"Filtering Pass Score <= {args.max_score_to_show}")

        print_explanations(criterion_ratings, args.max_score_to_show)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
