# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import json
from random import Random
from typing import Any

from mail import action


WEATHER_FORECAST_PARAMETERS = {
    "type": "object",
    "properties": {
        "location": {
            "type": "string",
            "description": "The location to get the weather forecast for",
        },
        "days_ahead": {
            "type": "integer",
            "description": "The number of days ahead to get the weather forecast for",
        },
        "metric": {
            "type": "boolean",
            "description": "Whether to use metric units",
        },
    },
    "required": ["location", "days_ahead", "metric"],
}


@action(
    name="get_weather_forecast",
    description="Get the weather forecast for a given location.",
    parameters=WEATHER_FORECAST_PARAMETERS,
)
async def get_weather_forecast(args: dict[str, Any]) -> str:
    """
    Dummy action that returns the weather "forecast" for a given location.
    """
    try:
        location = args["location"]
        days_ahead = args["days_ahead"]
        metric = args["metric"]
    except KeyError as e:
        return f"Error: {e} is required"

    # generate a random weather forecast
    # on any given day, the forecast should yield the same result for the same location
    # otherwise the weather agent will be confused
    day = datetime.datetime.now(datetime.UTC).day
    rng = Random()
    rng.seed(location + str(days_ahead) + str(day))
    forecast = {
        "location": location,
        "date": str(
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=days_ahead)
        ),
        "condition": rng.choice(
            [
                "clear",
                "mostly clear",
                "partly cloudy",
                "mostly cloudy",
                "overcast",
                "light precipitation",
                "moderate precipitation",
                "heavy precipitation",
            ]
        ),
        "temperature": rng.randint(-15, 35) if metric else rng.randint(5, 95),
        "units": "C" if metric else "F",
    }

    return json.dumps(forecast)
