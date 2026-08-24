"""Variable calculation for DCPs.

A DCP run carries a typed variable context. Values enter it three ways:
  * by declaration (parameters -- user-supplied or defaulted),
  * by regex extraction from command output,
  * by derivation (safe expressions computed from other variables).

``safe_eval`` evaluates a *restricted* expression AST: it can only read
variables from the context and apply a whitelisted set of operations and
string methods. Arbitrary code execution is not possible.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fncollect.session_ctx import RunContext

ALLOWED_TYPES = {"string", "int", "float", "ip", "enum", "password"}

_STRING_METHODS: dict[str, Callable[..., Any]] = {
    "upper": lambda s: s.upper(),
    "lower": lambda s: s.lower(),
    "strip": lambda s: s.strip(),
    "split": lambda s, *a: s.split(*a),
    "replace": lambda s, *a: s.replace(*a),
}

_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_CMPOPS: dict[type, Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


class VariableError(ValueError):
    pass


@dataclass
class Parameter:
    name: str
    type: str = "string"
    default: Any = None
    enum: list[Any] | None = None
    regex: str | None = None

    def validate(self, value: Any) -> Any:
        if self.type == "int":
            try:
                return int(value)
            except (TypeError, ValueError):
                raise VariableError(
                    f"parameter {self.name!r} must be an int, got {value!r}"
                ) from None
        if self.type == "float":
            try:
                return float(value)
            except (TypeError, ValueError):
                raise VariableError(
                    f"parameter {self.name!r} must be a float, got {value!r}"
                ) from None
        if self.type == "enum":
            if value not in (self.enum or []):
                raise VariableError(
                    f"parameter {self.name!r} must be one of {self.enum}, got {value!r}"
                )
            return value
        if self.type == "password":
            if not isinstance(value, str) or not value:
                raise VariableError(f"parameter {self.name!r} must be a non-empty string")
            return value
        value = str(value)
        if self.regex and not _match(self.regex, value):
            raise VariableError(
                f"parameter {self.name!r} does not match {self.regex!r}: {value!r}"
            )
        return value


def _match(regex: str, value: str) -> bool:
    import re

    return re.search(regex, value) is not None


class VariableContext:
    def __init__(self, parameters: list[Parameter] | None = None) -> None:
        self._values: dict[str, Any] = {}
        self._params: dict[str, Parameter] = {}
        for parameter in parameters or []:
            self._params[parameter.name] = parameter
            if parameter.default is not None:
                self.set(parameter.name, parameter.default, via="default")

    def declare(self, parameter: Parameter) -> None:
        self._params[parameter.name] = parameter

    def set(self, name: str, value: Any, via: str = "manual") -> None:
        parameter = self._params.get(name)
        if parameter is not None:
            value = parameter.validate(value)
        else:
            value = _coerce(value)
        self._values[name] = value

    def get(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError:
            raise VariableError(f"variable {name!r} is not set") from None

    def has(self, name: str) -> bool:
        return name in self._values

    def snapshot(self) -> dict[str, Any]:
        return dict(self._values)

    def record_artifacts(self, dcp_name: str, run: RunContext) -> None:
        import json

        run.write_text(
            Path("variables"),
            "variables.json",
            json.dumps(self.snapshot(), indent=2, sort_keys=True),
            "dcp-variables",
            {"dcp": dcp_name},
        )


def _coerce(value: Any) -> Any:
    if isinstance(value, str):
        return value
    return value


def safe_eval(expression: str, context: VariableContext) -> Any:
    """Evaluate a restricted expression against a variable context."""
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body, context)


def _eval_node(node, context: VariableContext) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return context.get(node.id)
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise VariableError(f"unsupported operator: {type(node.op).__name__}")
        return op(_eval_node(node.left, context), _eval_node(node.right, context))
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise VariableError("multiple comparisons are not supported")
        op = _CMPOPS.get(type(node.ops[0]))
        if op is None:
            raise VariableError(f"unsupported operator: {type(node.ops[0]).__name__}")
        return op(
            _eval_node(node.left, context),
            _eval_node(node.comparators[0], context),
        )
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = True
            for value in node.values:
                result = result and _eval_node(value, context)
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for value in node.values:
                result = result or _eval_node(value, context)
            return result
        raise VariableError("unsupported boolean operation")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, context)
    if isinstance(node, ast.Subscript):
        return _eval_node(node.value, context)[_eval_node(node.slice, context)]
    if isinstance(node, ast.Attribute):
        base = _eval_node(node.value, context)
        method = _STRING_METHODS.get(node.attr)
        if method is not None and isinstance(base, str):
            return method(base)
        raise VariableError(f"unsupported attribute: {node.attr!r}")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Attribute):
            raise VariableError("only string methods may be called")
        method = _STRING_METHODS.get(node.func.attr)
        if method is None:
            raise VariableError(f"unsupported method: {node.func.attr!r}")
        base = _eval_node(node.func.value, context)
        args = [_eval_node(a, context) for a in node.args]
        return method(base, *args)
    raise VariableError(f"unsupported expression node: {type(node).__name__}")


def render(template: str | None, context: VariableContext) -> str | None:
    """Substitute ``{{ name }}`` placeholders from the variable context."""
    if template is None or "{{" not in template:
        return template
    import re

    def repl(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        return str(context.get(name))

    return re.sub(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}", repl, template)
