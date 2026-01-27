# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Statistical calculation actions for the Data Analysis swarm.

These actions perform REAL statistical calculations (not dummy data).
"""

import json
import math
from collections import Counter
from typing import Any

from mail import action

# All available metrics
AVAILABLE_METRICS = [
    "count",
    "mean",
    "median",
    "mode",
    "std",
    "variance",
    "min",
    "max",
    "range",
    "sum",
    "percentile_25",
    "percentile_75",
    "iqr",
]


def _extract_numeric_values(data: list[Any]) -> list[float]:
    """Extract numeric values from data, filtering out non-numeric items."""
    values = []
    for item in data:
        if isinstance(item, int | float) and not math.isnan(item) and not math.isinf(item):
            values.append(float(item))
    return values


def _calculate_mean(values: list[float]) -> float:
    """Calculate arithmetic mean."""
    return sum(values) / len(values)


def _calculate_median(values: list[float]) -> float:
    """Calculate median value."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return sorted_vals[mid]


def _calculate_mode(values: list[float]) -> float | None:
    """Calculate mode (most frequent value)."""
    if not values:
        return None
    counter = Counter(values)
    max_count = max(counter.values())
    modes = [val for val, count in counter.items() if count == max_count]
    return modes[0] if len(modes) == 1 else None  # Return None if multi-modal


def _calculate_variance(values: list[float], mean: float) -> float:
    """Calculate population variance."""
    if len(values) < 2:
        return 0.0
    return sum((x - mean) ** 2 for x in values) / len(values)


def _calculate_std(values: list[float], mean: float) -> float:
    """Calculate population standard deviation."""
    return math.sqrt(_calculate_variance(values, mean))


def _calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate a given percentile."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    index = (percentile / 100) * (n - 1)
    lower = int(index)
    upper = lower + 1
    if upper >= n:
        return sorted_vals[-1]
    fraction = index - lower
    return sorted_vals[lower] + fraction * (sorted_vals[upper] - sorted_vals[lower])


CALCULATE_STATISTICS_PARAMETERS = {
    "type": "object",
    "properties": {
        "data": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Array of numeric values to analyze",
        },
        "metrics": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": AVAILABLE_METRICS,
            },
            "description": f"List of metrics to calculate. Available: {', '.join(AVAILABLE_METRICS)}",
        },
    },
    "required": ["data"],
}


@action(
    name="calculate_statistics",
    description="Calculate descriptive statistics for a numeric dataset.",
    parameters=CALCULATE_STATISTICS_PARAMETERS,
)
async def calculate_statistics(args: dict[str, Any]) -> str:
    """Calculate descriptive statistics on numeric data."""
    try:
        data = args["data"]
        metrics = args.get("metrics", ["count", "mean", "median", "std", "min", "max"])
    except KeyError as e:
        return f"Error: {e} is required"

    # Extract numeric values
    values = _extract_numeric_values(data)

    if not values:
        return json.dumps(
            {
                "error": "No valid numeric values found in data",
                "original_count": len(data),
                "valid_count": 0,
            }
        )

    # Calculate requested metrics
    results: dict[str, Any] = {
        "data_points": len(values),
        "original_count": len(data),
        "valid_count": len(values),
        "metrics": {},
    }

    # Pre-calculate common values
    mean = _calculate_mean(values)
    sorted_vals = sorted(values)

    for metric in metrics:
        if metric not in AVAILABLE_METRICS:
            results["metrics"][metric] = {"error": f"Unknown metric: {metric}"} # type: ignore
            continue

        try:
            if metric == "count":
                results["metrics"][metric] = len(values) # type: ignore
            elif metric == "mean":
                results["metrics"][metric] = round(mean, 4) # type: ignore
            elif metric == "median":
                results["metrics"][metric] = round(_calculate_median(values), 4) # type: ignore
            elif metric == "mode":
                mode = _calculate_mode(values)
                results["metrics"][metric] = ( # type: ignore
                    round(mode, 4) if mode is not None else "multimodal"
                )
            elif metric == "std":
                results["metrics"][metric] = round(_calculate_std(values, mean), 4) # type: ignore
            elif metric == "variance":
                results["metrics"][metric] = round(_calculate_variance(values, mean), 4) # type: ignore
            elif metric == "min":
                results["metrics"][metric] = round(min(values), 4) # type: ignore
            elif metric == "max":
                results["metrics"][metric] = round(max(values), 4) # type: ignore
            elif metric == "range":
                results["metrics"][metric] = round(max(values) - min(values), 4) # type: ignore
            elif metric == "sum":
                results["metrics"][metric] = round(sum(values), 4) # type: ignore
            elif metric == "percentile_25":
                results["metrics"][metric] = round(_calculate_percentile(values, 25), 4) # type: ignore
            elif metric == "percentile_75":
                results["metrics"][metric] = round(_calculate_percentile(values, 75), 4) # type: ignore
            elif metric == "iqr":
                q1 = _calculate_percentile(values, 25)
                q3 = _calculate_percentile(values, 75)
                results["metrics"][metric] = round(q3 - q1, 4) # type: ignore
        except Exception as e:
            results["metrics"][metric] = {"error": str(e)} # type: ignore

    # Add interpretation
    results["interpretation"] = _generate_interpretation(
        results["metrics"], len(values) # type: ignore
    )

    return json.dumps(results)


def _generate_interpretation(metrics: dict[str, Any], n: int) -> str:
    """Generate a human-readable interpretation of the statistics."""
    parts = []

    parts.append(f"Analysis based on {n} data points.")

    if "mean" in metrics and "median" in metrics:
        mean = metrics["mean"]
        median = metrics["median"]
        if isinstance(mean, int | float) and isinstance(median, int | float):
            if abs(mean - median) / max(abs(mean), 0.001) > 0.1:
                if mean > median:
                    parts.append(
                        "Data is right-skewed (mean > median), indicating some high outliers."
                    )
                else:
                    parts.append(
                        "Data is left-skewed (mean < median), indicating some low outliers."
                    )
            else:
                parts.append("Data appears roughly symmetric (mean ≈ median).")

    if "std" in metrics and "mean" in metrics:
        std = metrics["std"]
        mean = metrics["mean"]
        if isinstance(std, int | float) and isinstance(mean, int | float) and mean != 0:
            cv = abs(std / mean)
            if cv > 1:
                parts.append("High variability in the data (CV > 100%).")
            elif cv > 0.3:
                parts.append("Moderate variability in the data.")
            else:
                parts.append("Low variability, data is relatively consistent.")

    return " ".join(parts)


RUN_CORRELATION_PARAMETERS = {
    "type": "object",
    "properties": {
        "x": {
            "type": "array",
            "items": {"type": "number"},
            "description": "First variable (array of numbers)",
        },
        "y": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Second variable (array of numbers)",
        },
    },
    "required": ["x", "y"],
}


@action(
    name="run_correlation",
    description="Calculate the Pearson correlation coefficient between two variables.",
    parameters=RUN_CORRELATION_PARAMETERS,
)
async def run_correlation(args: dict[str, Any]) -> str:
    """Calculate Pearson correlation between two variables."""
    try:
        x_data = args["x"]
        y_data = args["y"]
    except KeyError as e:
        return f"Error: {e} is required"

    # Extract numeric values and pair them
    x_values = _extract_numeric_values(x_data)
    y_values = _extract_numeric_values(y_data)

    if len(x_values) != len(y_values):
        # Truncate to shorter length
        min_len = min(len(x_values), len(y_values))
        x_values = x_values[:min_len]
        y_values = y_values[:min_len]

    n = len(x_values)

    if n < 3:
        return json.dumps(
            {
                "error": "Need at least 3 paired data points for correlation",
                "data_points": n,
            }
        )

    # Calculate Pearson correlation coefficient
    mean_x = sum(x_values) / n
    mean_y = sum(y_values) / n

    # Calculate covariance and standard deviations
    covariance = (
        sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values)) / n
    )
    std_x = math.sqrt(sum((x - mean_x) ** 2 for x in x_values) / n)
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in y_values) / n)

    if std_x == 0 or std_y == 0:
        return json.dumps(
            {
                "error": "Cannot calculate correlation when one variable has zero variance",
                "std_x": std_x,
                "std_y": std_y,
            }
        )

    r = covariance / (std_x * std_y)

    # Calculate R-squared
    r_squared = r**2

    # Determine strength and direction
    if abs(r) >= 0.8:
        strength = "strong"
    elif abs(r) >= 0.5:
        strength = "moderate"
    elif abs(r) >= 0.3:
        strength = "weak"
    else:
        strength = "very weak or no"

    direction = "positive" if r > 0 else "negative" if r < 0 else "no"

    result = {
        "correlation_coefficient": round(r, 4),
        "r_squared": round(r_squared, 4),
        "data_points": n,
        "strength": strength,
        "direction": direction,
        "interpretation": f"There is a {strength} {direction} correlation (r={r:.3f}). "
        f"The R² value of {r_squared:.3f} means that approximately "
        f"{r_squared * 100:.1f}% of the variance in Y can be explained by X.",
        "x_stats": {
            "mean": round(mean_x, 4),
            "std": round(std_x, 4),
        },
        "y_stats": {
            "mean": round(mean_y, 4),
            "std": round(std_y, 4),
        },
    }

    return json.dumps(result)
