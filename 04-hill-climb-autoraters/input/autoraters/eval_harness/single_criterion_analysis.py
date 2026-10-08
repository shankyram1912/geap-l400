"""Single Criterion Agreement Analysis Tool.

Inspect the detailed work items vs. evaluation passes (N x k) table for a single criterion,
and view summary statistics.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List

import pandas as pd
from tabulate import tabulate

from eval_harness.metrics_calc import compute_criterion_stats
from eval_harness.utils import load_eval_ratings_by_criterion, build_grades_dataframe, format_val


def format_cell(val: Any) -> str:
    """Formats a cell value for clean string display in the output table.

    Integers are formatted as standard integer strings (e.g., '3'), floats are
    formatted to 2 decimal places (e.g., '3.60'), and missing/NaN values are
    returned as 'NA'. Other values are converted directly to strings.

    Args:
        val: The value to format.

    Returns:
        The formatted string representation of the value.
    """
    if isinstance(val, (int, float)) and not pd.isna(val):
        if val == int(val):
            return str(int(val))
        return f"{val:.2f}"
    return str(val) if not pd.isna(val) else "NA"



def get_summary_metrics_str(criterion_id: str, criterion_name: str, stats: Dict[str, Any]) -> str:
    """Formats and returns the criterion name and summary metrics as a string.

    Args:
        criterion_id: The ID of the criterion.
        criterion_name: The name of the criterion.
        stats: A dictionary containing computed stats from metrics_calc.

    Returns:
        The formatted string summary.
    """
    lines = []
    lines.append(f"=========================================")
    lines.append(f"🔍 Criterion ID: {criterion_id}")
    lines.append(f"📋 Name:         {criterion_name}")
    lines.append(f"=========================================")

    # Format custom range strings with items/passes for single_criterion_analysis report display
    max_range_lots = stats["max_range_report_items"]
    max_range_lot_val = stats["max_range_report"]
    if len(max_range_lots) > 3:
        lots_str = f"{', '.join(max_range_lots[:3])} (+{len(max_range_lots)-3} more)"
    else:
        lots_str = ", ".join(max_range_lots)
    max_range_lot_str = f"{max_range_lot_val:.0f} (Lot: {lots_str})" if max_range_lots else "0"

    max_range_passes = stats["max_range_pass_items"]
    max_range_pass_val = stats["max_range_pass"]
    if len(max_range_passes) > 3:
        passes_str = f"{', '.join(max_range_passes[:3])} (+{len(max_range_passes)-3} more)"
    else:
        passes_str = ", ".join(max_range_passes)
    max_range_pass_str = f"{max_range_pass_val:.0f} (Pass: {passes_str})" if max_range_passes else "0"

    summary_table = [
        {"Metric": "Mean Score", "Short Name": "mean", "Value": format_val(stats["mean"], "{:.4f}")},
        {"Metric": "Min All Ratings", "Short Name": "min rating", "Value": format_val(stats["min_rating"], "{:.0f}")},
        {"Metric": "Max All Ratings", "Short Name": "max rating", "Value": format_val(stats["max_rating"], "{:.0f}")},
        {"Metric": "Widest Range Single Report", "Short Name": "max range report", "Value": max_range_lot_str},
        {"Metric": "Widest Range Single Pass", "Short Name": "max range pass", "Value": max_range_pass_str},
        {"Metric": "StdDev of Report Means", "Short Name": "sd report means", "Value": format_val(stats["sd_report_means"], "{:.4f}")},
        {"Metric": "StdDev of Pass Means", "Short Name": "sd pass means", "Value": format_val(stats["sd_pass_means"], "{:.4f}")},
        {"Metric": "Mean Pairwise Percent Agreement of Report Ratings", "Short Name": "pairwise %_agree", "Value": format_val(stats["mean_pa"], "{:.2%}")},
        {"Metric": "Krippendorff's Alpha", "Short Name": "alpha", "Value": "N/A [Single Pass]" if stats["k"] <= 1 else format_val(stats["alpha"], "{:.4f}")},
    ]
    lines.append("\n📈 Criterion Metrics Summary:")
    summary_str = tabulate(summary_table, headers="keys", tablefmt="github")
    lines.append(summary_str)
    
    first_line_summary = summary_str.split("\n")[0] if summary_str else ""
    summary_width = len(first_line_summary)
    if summary_width > 0:
        lines.append("=" * summary_width)

    return "\n".join(lines)


def get_grades_matrix_str(grades_df: pd.DataFrame, stats: Dict[str, Any]) -> str:
    """Builds, post-processes, and returns the thin Grades Matrix table as a string.

    Args:
        grades_df: pivoted DataFrame of scores.
        stats: A dictionary containing computed stats from metrics_calc.

    Returns:
        The formatted Grades Matrix table string.
    """
    num_items = stats["N"]
    num_passes = stats["k"]
    item_min = stats["item_min"]
    item_max = stats["item_max"]
    item_range = stats["item_range"]
    item_mean = stats["item_mean"]
    item_std = stats["item_std"]

    pass_mean = stats["pass_mean"]
    pass_std = stats["pass_std"]
    pass_min = stats["pass_min"]
    pass_max = stats["pass_max"]
    pass_range = stats["pass_range"]

    lines = []
    lines.append(f"\n📊 Grades Matrix (N={num_items} items x k={num_passes} passes):")
    display_df = grades_df.copy()

    item_min_col = "min"
    item_max_col = "max"
    item_range_col = "range"
    item_mean_col = "mean"
    item_std_col = "std"
    item_pa_col = "%_pw_ag"

    display_df[item_min_col] = item_min
    display_df[item_max_col] = item_max
    display_df[item_range_col] = item_range
    display_df[item_mean_col] = item_mean
    display_df[item_std_col] = item_std
    display_df[item_pa_col] = stats["item_pa"].map(lambda x: f"{x*100:.0f}%" if not pd.isna(x) else "NA")

    # Create bottom rows
    stat_rows = ["pass mean", "pass std", "pass min", "pass max", "pass range"]
    extra_df = pd.DataFrame(index=stat_rows, columns=display_df.columns)

    for col in grades_df.columns:
        extra_df.loc["pass mean", col] = pass_mean[col]
        extra_df.loc["pass std", col] = pass_std[col]
        extra_df.loc["pass min", col] = pass_min[col]
        extra_df.loc["pass max", col] = pass_max[col]
        extra_df.loc["pass range", col] = pass_range[col]

    # Fill intersection cells with hyphens
    for stat in stat_rows:
        extra_df.loc[stat, item_min_col] = "-"
        extra_df.loc[stat, item_max_col] = "-"
        extra_df.loc[stat, item_range_col] = "-"
        extra_df.loc[stat, item_mean_col] = "-"
        extra_df.loc[stat, item_std_col] = "-"
        extra_df.loc[stat, item_pa_col] = "-"

    # Concatenate and reset index
    display_df = pd.concat([display_df, extra_df])
    display_df = display_df.map(format_cell)
    display_df = display_df.reset_index().rename(columns={"index": "eval_id"})

    raw_table_str = tabulate(display_df, headers="keys", tablefmt="github", showindex=False)
    
    # Post-process the table to keep it compact for best chance it doesn't line break printing in cloud shell.
    thinned_lines = []
    for line in raw_table_str.strip().split("\n"):
        if not line.startswith("|"):
            thinned_lines.append(line)
            continue
        parts = line.split("|")
        if len(parts) >= 8:
            trim_mapping = {-7: 2, -6: 2, -5: 2, -4: 1}
            for idx, trim_amount in trim_mapping.items():
                for _ in range(trim_amount):
                    if parts[idx].endswith(" "):
                        parts[idx] = parts[idx][:-1]
                    elif parts[idx].endswith("-"):
                        parts[idx] = parts[idx][:-1]
        thinned_lines.append("|".join(parts))
    table_str = "\n".join(thinned_lines)
    lines.append(table_str)

    first_line = table_str.split("\n")[0] if table_str else ""
    table_width = len(first_line)
    if table_width > 0:
        lines.append("=" * table_width)

    return "\n".join(lines)



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze detailed ratings and rationales for a single criterion."
    )
    parser.add_argument(
        "--run_geap_eval_out",
        required=True,
        help="Path to eval calls and responoses output by run_geap_eval.py",
    )
    parser.add_argument(
        "--criterion",
        required=True,
        help="Criterion ID to analyze",
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
        
        grades_df = build_grades_dataframe(criterion_ratings)
        stats = compute_criterion_stats(grades_df)

        summary_str = get_summary_metrics_str(args.criterion, criterion_name, stats)
        grades_str = get_grades_matrix_str(grades_df, stats)

        # Print to console
        print(summary_str)
        print(grades_str)



    except Exception as e:
        print(f"❌ Error exploring criterion: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
