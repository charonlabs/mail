# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Data processing actions for the Data Analysis swarm."""

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from random import Random
from typing import Any

from mail import action

# Dataset templates with generators
DATASET_GENERATORS = {
    "sales": {
        "columns": ["date", "product", "quantity", "revenue", "region"],
        "description": "Sales transaction data",
    },
    "users": {
        "columns": [
            "user_id",
            "signup_date",
            "age",
            "subscription_type",
            "activity_score",
        ],
        "description": "User account data",
    },
    "inventory": {
        "columns": [
            "product_id",
            "category",
            "stock_level",
            "reorder_point",
            "unit_cost",
        ],
        "description": "Inventory tracking data",
    },
    "weather": {
        "columns": ["date", "temperature", "humidity", "precipitation", "wind_speed"],
        "description": "Daily weather observations",
    },
}

PRODUCTS = [
    "Widget A",
    "Widget B",
    "Gadget Pro",
    "Gadget Lite",
    "Service Plan",
    "Accessory Pack",
]
REGIONS = ["North", "South", "East", "West", "Central"]
SUBSCRIPTION_TYPES = ["free", "basic", "pro", "enterprise"]
CATEGORIES = ["Electronics", "Furniture", "Clothing", "Food", "Tools"]


def _generate_sales_row(
    rng: Random, row_idx: int, base_date: datetime
) -> dict[str, Any]:
    """Generate a single sales row."""
    date = base_date + timedelta(days=rng.randint(0, 365))
    product = rng.choice(PRODUCTS)
    quantity = rng.randint(1, 100)
    unit_price = rng.uniform(10.0, 500.0)
    revenue = round(quantity * unit_price, 2)
    region = rng.choice(REGIONS)

    return {
        "date": date.strftime("%Y-%m-%d"),
        "product": product,
        "quantity": quantity,
        "revenue": revenue,
        "region": region,
    }


def _generate_users_row(
    rng: Random, row_idx: int, base_date: datetime
) -> dict[str, Any]:
    """Generate a single user row."""
    signup_date = base_date + timedelta(days=rng.randint(0, 730))
    age = rng.randint(18, 75)
    subscription = rng.choice(SUBSCRIPTION_TYPES)
    activity = round(rng.uniform(0.0, 100.0), 1)

    return {
        "user_id": f"USR-{1000 + row_idx:05d}",
        "signup_date": signup_date.strftime("%Y-%m-%d"),
        "age": age,
        "subscription_type": subscription,
        "activity_score": activity,
    }


def _generate_inventory_row(
    rng: Random, row_idx: int, base_date: datetime
) -> dict[str, Any]:
    """Generate a single inventory row."""
    stock = rng.randint(0, 1000)
    reorder = rng.randint(10, 200)
    cost = round(rng.uniform(1.0, 100.0), 2)

    return {
        "product_id": f"PROD-{row_idx + 1:04d}",
        "category": rng.choice(CATEGORIES),
        "stock_level": stock,
        "reorder_point": reorder,
        "unit_cost": cost,
    }


def _generate_weather_row(
    rng: Random, row_idx: int, base_date: datetime
) -> dict[str, Any]:
    """Generate a single weather row."""
    date = base_date + timedelta(days=row_idx)
    # Temperature varies seasonally
    day_of_year = (date - datetime(date.year, 1, 1, tzinfo=UTC)).days
    seasonal_factor = abs(day_of_year - 182) / 182  # 0 at mid-year, 1 at ends
    base_temp = 20 - (seasonal_factor * 15)  # Warmer in summer
    temp = round(base_temp + rng.uniform(-10, 10), 1)

    return {
        "date": date.strftime("%Y-%m-%d"),
        "temperature": temp,
        "humidity": rng.randint(20, 95),
        "precipitation": round(rng.uniform(0, 50) if rng.random() < 0.3 else 0, 1),
        "wind_speed": round(rng.uniform(0, 40), 1),
    }


GENERATORS = {
    "sales": _generate_sales_row,
    "users": _generate_users_row,
    "inventory": _generate_inventory_row,
    "weather": _generate_weather_row,
}


GENERATE_SAMPLE_DATA_PARAMETERS = {
    "type": "object",
    "properties": {
        "dataset": {
            "type": "string",
            "enum": ["sales", "users", "inventory", "weather"],
            "description": "The type of sample dataset to generate",
        },
        "rows": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "description": "Number of rows to generate (default: 50, max: 1000)",
        },
    },
    "required": ["dataset"],
}


@action(
    name="generate_sample_data",
    description="Generate sample data for testing and demonstration purposes.",
    parameters=GENERATE_SAMPLE_DATA_PARAMETERS,
)
async def generate_sample_data(args: dict[str, Any]) -> str:
    """Generate sample data for a specified dataset type."""
    try:
        dataset = args["dataset"]
        rows = args.get("rows", 50)
    except KeyError as e:
        return f"Error: {e} is required"

    if dataset not in DATASET_GENERATORS:
        return json.dumps(
            {
                "error": f"Unknown dataset: {dataset}",
                "available_datasets": list(DATASET_GENERATORS.keys()),
            }
        )

    if rows < 1 or rows > 1000:
        return json.dumps({"error": "Rows must be between 1 and 1000"})

    # Generate deterministic data based on dataset name and current day
    today = datetime.now(UTC)
    seed = hash(dataset + today.strftime("%Y-%m-%d"))
    rng = Random(seed)

    base_date = datetime(today.year - 1, 1, 1, tzinfo=UTC)
    generator = GENERATORS[dataset]

    data = []
    for i in range(rows):
        row = generator(rng, i, base_date)
        data.append(row)

    return json.dumps(
        {
            "dataset": dataset,
            "description": DATASET_GENERATORS[dataset]["description"],
            "columns": DATASET_GENERATORS[dataset]["columns"],
            "row_count": len(data),
            "data": data,
        }
    )


PARSE_CSV_PARAMETERS = {
    "type": "object",
    "properties": {
        "data": {
            "type": "string",
            "description": "The CSV data as a string (with headers in first row)",
        },
    },
    "required": ["data"],
}


@action(
    name="parse_csv",
    description="Parse CSV data string into structured JSON format.",
    parameters=PARSE_CSV_PARAMETERS,
)
async def parse_csv(args: dict[str, Any]) -> str:
    """Parse CSV data into structured JSON."""
    try:
        csv_data = args["data"]
    except KeyError as e:
        return f"Error: {e} is required"

    if not csv_data.strip():
        return json.dumps({"error": "CSV data cannot be empty"})

    try:
        reader = csv.DictReader(io.StringIO(csv_data))
        columns = reader.fieldnames

        if not columns:
            return json.dumps({"error": "No header row found in CSV"})

        data = []
        errors: list[str] = []
        for i, row in enumerate(reader):
            # Try to convert numeric values
            parsed_row: dict[str, Any] = {}
            for col, val in row.items():
                if val is None or val == "":
                    parsed_row[col] = None  # type: ignore
                else:
                    # Try to parse as number
                    try:
                        if "." in val:
                            parsed_row[col] = float(val)
                        else:
                            parsed_row[col] = int(val)
                    except ValueError:
                        parsed_row[col] = val

            data.append(parsed_row)

        # Detect column types
        column_types = {}
        for col in columns:
            types_seen = set()
            for row in data[:100]:  # Sample first 100 rows
                val = row.get(col)
                if val is None:
                    continue
                types_seen.add(type(val).__name__)

            if types_seen == {"int"}:
                column_types[col] = "integer"
            elif types_seen <= {"int", "float"}:
                column_types[col] = "numeric"
            else:
                column_types[col] = "string"

        return json.dumps(
            {
                "success": True,
                "columns": list(columns),
                "column_types": column_types,
                "row_count": len(data),
                "data": data,
                "parse_errors": errors if errors else None,
            }
        )

    except csv.Error as e:
        return json.dumps({"error": f"CSV parsing error: {str(e)}"})
