from mail.api import MAILAction

action_get_weather_forecast = MAILAction(
    name="get_weather_forecast",
    description="Get the weather forecast for a given location",
    parameters={
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
    function="mail.examples.weather_dummy.actions:get_weather_forecast",
)
