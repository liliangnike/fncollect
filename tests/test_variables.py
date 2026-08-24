"""Tests for the variable-calculation layer (context, extraction,
derivation, templating, validation)."""

import pytest

from fncollect.dcp import execute_dcp, parse_dcp
from fncollect.variables import (
    Parameter,
    VariableContext,
    VariableError,
    render,
    safe_eval,
)
from fncollect.vendors.mock import MockVendor


@pytest.fixture
def run_ctx(tmp_path):
    from fncollect.config import LoggingConfig, RunConfig
    from fncollect.logging_setup import build_logger
    from fncollect.session_ctx import RunContext

    return RunContext(
        RunConfig(output_dir="."),
        tmp_path,
        logger=build_logger(config=LoggingConfig()),
    )


def test_parameter_validation_int():
    context = VariableContext([Parameter(name="n", type="int")])
    context.set("n", "42", via="test")
    assert context.get("n") == 42
    with pytest.raises(VariableError):
        context.set("n", "not-an-int", via="test")


def test_parameter_enum_validation():
    context = VariableContext([Parameter(name="slot", type="enum", enum=["a", "b"])])
    context.set("slot", "a", via="test")
    with pytest.raises(VariableError):
        context.set("slot", "z", via="test")


def test_safe_eval_expression_uses_context():
    context = VariableContext()
    context.set("sw_version", "1.2.3", via="test")
    assert safe_eval("sw_version.split('.')[0]", context) == "1"


def test_safe_eval_rejects_code():
    context = VariableContext()
    context.set("x", "1", via="test")
    with pytest.raises(VariableError):
        safe_eval("__import__('os').system('echo hi')", context)


def test_render_substitutes_variables():
    context = VariableContext()
    context.set("ont_id", "7", via="test")
    assert render("show ont {{ ont_id }}", context) == "show ont 7"


async def test_extraction_and_templating_end_to_end(run_ctx):
    dcp = parse_dcp(
        """
name: collect_with_vars
vendor: mock
steps:
  - id: s1
    command: "show version"
    extract:
      - {name: model, regex: "Model: (\\\\S+)", group: 1}
  - id: s2
    command: "show ont {{ ont_id }}"
    save: "ont/{{ ont_id }}.txt"
"""
    )
    mock = MockVendor()
    device = mock.create_device(mock.device_info())
    results = await execute_dcp(dcp, device, run_ctx, seed_variables={"ont_id": "2"})
    steps = {s["id"]: s for s in results["steps"]}
    assert steps["s1"]["ok"] is True
    assert steps["s2"]["ok"] is True
    assert "ont/2.txt" in str(steps["s2"]["artifact"])
    variables = (run_ctx.dir / "variables" / "variables.json").read_text()
    assert '"mock-OLT-1000"' in variables
