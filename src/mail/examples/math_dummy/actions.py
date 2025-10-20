# SPDX-License-Identifier: Apache-2.0

"""Utility actions exposed by the math example agent."""

from __future__ import annotations

import ast
import json
import re
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from typing import Any, Final, Union

from mail import action

Number = Union[int, Decimal]

# Extended-precision constants to keep deterministic values for math literals.
_CONSTANTS: Final[dict[str, Decimal]] = {
    "pi": Decimal("3.14159265358979323846264338327950288419716939937510"),
    "tau": Decimal("6.28318530717958647692528676655900576839433879875021"),
    "e": Decimal("2.71828182845904523536028747135266249775724709369996"),
}

_MIN_PRECISION: Final[int] = 64
_MAX_PRECISION: Final[int] = 4096

CALCULATE_EXPRESSION_PARAMETERS: Final[dict[str, Any]] = {
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
            "description": (
                "Optional number of decimal places for the formatted result."
            ),
        },
    },
    "required": ["expression"],
}


class _CalculatorError(ValueError):
    """Raised when the calculator cannot safely evaluate an expression."""


def _estimate_precision(expr: str) -> int:
    digit_groups = re.findall(r"\d+", expr)
    if not digit_groups:
        return _MIN_PRECISION
    total_digits = sum(len(group) for group in digit_groups)
    return max(_MIN_PRECISION, min(_MAX_PRECISION, total_digits * 2))


def _to_decimal(value: Number) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def _format_decimal(value: Decimal, precision: int | None) -> str:
    dec = value
    if precision is not None:
        quant = Decimal(1).scaleb(-precision)
        dec = dec.quantize(quant, rounding=ROUND_HALF_EVEN)
        formatted = format(dec, "f")
        return formatted

    formatted = format(dec, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
        if not formatted:
            formatted = "0"
    return formatted


def _format_result(value: Number, precision: int | None) -> tuple[str, str, bool]:
    if isinstance(value, int):
        dec_value = Decimal(value)
        formatted = _format_decimal(dec_value, precision)
        exact = str(value)
        return exact, formatted, True

    exact = _format_decimal(value, None)
    formatted = _format_decimal(value, precision)
    is_integer = value == value.to_integral_value()
    return exact, formatted, is_integer


def _apply_unary(op: ast.unaryop, operand: Number) -> Number:
    if isinstance(op, ast.UAdd):
        return operand
    if isinstance(op, ast.USub):
        return -operand
    raise _CalculatorError("Unsupported unary operator")


def _apply_binop(op: ast.operator, left: Number, right: Number) -> Number:
    if isinstance(left, int) and isinstance(right, int):
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Pow):
            if right < 0:
                left_dec = _to_decimal(left)
                return left_dec**right
            return left**right
        if isinstance(op, ast.FloorDiv):
            if right == 0:
                raise ZeroDivisionError
            return left // right
        if isinstance(op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError
            return left % right
        if isinstance(op, ast.Div):
            left_dec = _to_decimal(left)
            right_dec = _to_decimal(right)
            return left_dec / right_dec
        raise _CalculatorError("Unsupported operator")

    left_dec = _to_decimal(left)
    right_dec = _to_decimal(right)

    if isinstance(op, ast.Add):
        return left_dec + right_dec
    if isinstance(op, ast.Sub):
        return left_dec - right_dec
    if isinstance(op, ast.Mult):
        return left_dec * right_dec
    if isinstance(op, ast.Div):
        return left_dec / right_dec
    if isinstance(op, ast.FloorDiv):
        if right_dec == 0:
            raise ZeroDivisionError
        result = left_dec // right_dec
        if result == result.to_integral_value():
            return int(result)
        return result
    if isinstance(op, ast.Mod):
        if right_dec == 0:
            raise ZeroDivisionError
        return left_dec % right_dec
    if isinstance(op, ast.Pow):
        if isinstance(right, int):
            return left_dec**right
        raise _CalculatorError("Exponent must be an integer")
    raise _CalculatorError("Unsupported operator")


def _eval_node(node: ast.AST, source: str) -> Number:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, source)

    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or value is None:
            raise _CalculatorError("Unsupported literal")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            # Reconstruct via source to avoid binary float artifacts if available.
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                return Decimal(segment.replace("_", ""))
            return Decimal(str(value))
        raise _CalculatorError("Only numeric literals are supported")

    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise _CalculatorError(f"Unknown constant '{node.id}'")

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, source)
        right = _eval_node(node.right, source)
        return _apply_binop(node.op, left, right)

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, source)
        return _apply_unary(node.op, operand)

    raise _CalculatorError("Unsupported syntax in expression")


@action(
    name="calculate_expression",
    description=(
        "Evaluate a basic arithmetic expression with +, -, *, /, %, //, **, and "
        "parentheses."
    ),
    parameters=CALCULATE_EXPRESSION_PARAMETERS,
)
async def calculate_expression(args: dict[str, Any]) -> str:
    """Evaluate a basic arithmetic expression and return a structured JSON payload.

    Supported grammar:
    - numeric literals (integers or decimals)
    - parentheses
    - operators: +, -, *, /, //, %, **
    - unary + and -
    - constants: e, pi, tau

    When provided, ``precision`` (0-12) controls rounding in ``formatted_result``.
    """

    expression = args.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        return "Error: 'expression' must be a non-empty string"

    precision = args.get("precision")
    if precision is not None:
        if not isinstance(precision, int) or not (0 <= precision <= 12):
            return "Error: 'precision' must be an integer between 0 and 12"

    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError:
        return "Error: invalid syntax"

    try:
        with localcontext() as ctx:
            ctx.prec = _estimate_precision(expression)
            result: Number = _eval_node(parsed, expression)
    except _CalculatorError as exc:
        return f"Error: {exc}"
    except ZeroDivisionError:
        return "Error: division by zero"
    except (InvalidOperation, OverflowError):
        return "Error: unable to evaluate expression"

    if isinstance(result, Decimal) and not result.is_finite():
        return "Error: result is not a finite number"

    exact_result, formatted_result, is_integer = _format_result(result, precision)

    payload = {
        "expression": expression,
        "result": exact_result,
        "formatted_result": formatted_result,
        "precision": precision,
        "is_integer": is_integer,
    }

    return json.dumps(payload)
