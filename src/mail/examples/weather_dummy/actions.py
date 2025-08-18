import datetime
import json
import random
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
    forecast = {
        "location": location,
        "date": str(datetime.datetime.now() + datetime.timedelta(days=days_ahead)),
        "condition": random.choice(
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
        "temperature": random.randint(-15, 35) if metric else random.randint(5, 95),
        "units": "C" if metric else "F",
    }

    return json.dumps(forecast)
