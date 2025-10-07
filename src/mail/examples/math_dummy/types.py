from mail.api import MAILAction

action_calculate_expression = MAILAction(
    name="calculate_expression",
    description="Evaluate a basic arithmetic expression with +, -, *, /, %, //, **, and parentheses.",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The arithmetic expression to evaluate.",
            },
            "precision": {
                "type": "integer",
                "minimum": 0,
                "maximum": 12,
                "description": "Optional number of decimal places for the formatted result.",
            },
        },
        "required": ["expression"],
    },
    function="mail.examples.math_dummy.actions:calculate_expression",
)
