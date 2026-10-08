"""Shared Metrics Calculation Engine for Autorater Lab."""

import os
import sys
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from krippendorff_alpha.metric import krippendorff_alpha
from krippendorff_alpha.schema import DataTypeEnum


def krippendorff_alpha_interval(grades_df: pd.DataFrame) -> float:
    """Computes Krippendorff's Alpha for interval data using the krippendorff-aleph-alpha package.

    Args:
        grades_df: A 2D Pandas DataFrame of shape (N, k).

    Returns:
        float: Krippendorff's Alpha.
    """
    df = grades_df.dropna(how="all")
    N, k = df.shape

    if k <= 1 or N == 0:
        return float("nan")

    try:
        # Transpose grades_df to match the library's expected shape:
        # Rows = annotators (passes), Columns = subjects (lots)
        res = krippendorff_alpha(df.T, DataTypeEnum.INTERVAL)
        return float(res["alpha"])
    except Exception:
        return float("nan")


def compute_percent_agreement_row(row: pd.Series) -> float:
    """Computes percent agreement for a single row of ratings (excluding NaNs)."""
    v = row.dropna().values
    n = len(v)
    if n <= 1:
        return np.nan
    unique_vals, counts = np.unique(v, return_counts=True)
    agreeing_pairs = sum(c * (c - 1) for c in counts)
    total_pairs = n * (n - 1)
    return agreeing_pairs / total_pairs


def compute_criterion_stats(grades_df: pd.DataFrame) -> Dict[str, Any]:
    """Computes inter-rater reliability and descriptive statistics for a work items x raters table.

    Args:
        grades_df: A Pandas DataFrame of shape containing rating scores.
            - Rows represent unique work items.
            - Columns represent distinct raters.
            - Cells contain numeric rating values (or NaN if missing).

    Returns:
        A dictionary containing computed metrics and statistical summaries:
            - "N" (int): Number of work items.
            - "k" (int): Number of raters/passes.
            - "item_min" (pd.Series): Minimum rating for each work item.
            - "item_max" (pd.Series): Maximum rating for each work item.
            - "item_range" (pd.Series): Range (max - min) of ratings for each work item.
            - "item_mean" (pd.Series): Mean rating for each work item across passes.
            - "item_std" (pd.Series): Standard deviation of ratings for each work item.
            - "item_pa" (pd.Series): Percent agreement of ratings for each work item.
            - "pass_mean" (pd.Series): Mean rating score of each pass across items.
            - "pass_std" (pd.Series): Standard deviation of ratings for each pass.
            - "pass_min" (pd.Series): Minimum rating score for each pass.
            - "pass_max" (pd.Series): Maximum rating score for each pass.
            - "pass_range" (pd.Series): Range of ratings for each pass.
            - "mean" (float): Overall mean score across all items and passes.
            - "min_rating" (float): Minimum rating score observed globally.
            - "max_rating" (float): Maximum rating score observed globally.
            - "max_range_report" (float): The maximum rating range observed on any single work item.
            - "max_range_report_items" (List[str]): List of work items that exhibited the max range.
            - "max_range_pass" (float): The maximum rating range observed on any single pass.
            - "max_range_pass_items" (List[str]): List of passes that exhibited the max range.
            - "sd_report_means" (float): Standard deviation of the mean rating scores of work items.
            - "sd_pass_means" (float): Standard deviation of the mean rating scores of passes.
            - "alpha" (float): Krippendorff's Alpha inter-rater agreement coefficient.
            - "mean_pa" (float): Average percent agreement across all work items.
            - "sigma" (float): Average intra-item standard deviation.
            - "total_std" (float): Global standard deviation of all rating scores.
    """
    N, k = grades_df.shape

    # Row (Item) statistics
    item_min = grades_df.min(axis=1)
    item_max = grades_df.max(axis=1)
    item_range = item_max - item_min
    item_mean = grades_df.mean(axis=1)
    item_std = grades_df.std(axis=1, ddof=1) if k > 1 else pd.Series(np.nan, index=grades_df.index)
    item_pa = grades_df.apply(compute_percent_agreement_row, axis=1)

    # Column (Pass) statistics
    pass_mean = grades_df.mean(axis=0)
    pass_std = grades_df.std(axis=0, ddof=1) if N > 1 else pd.Series(np.nan, index=grades_df.columns)
    pass_min = grades_df.min(axis=0)
    pass_max = grades_df.max(axis=0)
    pass_range = pass_max - pass_min

    # Scalar Metrics
    mean_val = np.nanmean(grades_df.values)
    min_rating = np.nanmin(grades_df.values)
    max_rating = np.nanmax(grades_df.values)

    max_range_report_val = item_range.max() if k > 1 else 0
    max_range_report_items = item_range[item_range == max_range_report_val].index.tolist() if k > 1 else []

    max_range_pass_val = pass_range.max() if N > 1 else 0
    max_range_pass_items = pass_range[pass_range == max_range_pass_val].index.tolist() if N > 1 else []

    sd_report_means = item_mean.std(ddof=1) if N > 1 else 0
    sd_pass_means = pass_mean.std(ddof=1) if k > 1 else 0
    alpha = krippendorff_alpha_interval(grades_df)
    mean_pa = item_pa.mean()
    
    report_sigmas = grades_df.std(axis=1, ddof=1) if k > 1 else pd.Series(np.nan, index=grades_df.index)
    sigma = report_sigmas.mean() if k > 1 else np.nan
    total_std = np.nanstd(grades_df.values, ddof=1)

    return {
        "N": N,
        "k": k,
        "item_min": item_min,
        "item_max": item_max,
        "item_range": item_range,
        "item_mean": item_mean,
        "item_std": item_std,
        "item_pa": item_pa,
        "pass_mean": pass_mean,
        "pass_std": pass_std,
        "pass_min": pass_min,
        "pass_max": pass_max,
        "pass_range": pass_range,
        "mean": mean_val,
        "min_rating": min_rating,
        "max_rating": max_rating,
        "max_range_report": max_range_report_val,
        "max_range_report_items": max_range_report_items,
        "max_range_pass": max_range_pass_val,
        "max_range_pass_items": max_range_pass_items,
        "sd_report_means": sd_report_means,
        "sd_pass_means": sd_pass_means,
        "alpha": alpha,
        "mean_pa": mean_pa,
        "sigma": sigma,
        "total_std": total_std,
    }
