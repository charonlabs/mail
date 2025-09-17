import datetime
import json
from random import Random
from typing import Any


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
