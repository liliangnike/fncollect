
import pytest

from fncollect.config import LoggingConfig, RunConfig
from fncollect.logging_setup import build_logger
from fncollect.session_ctx import RunContext


@pytest.fixture
def run_ctx(tmp_path):
    cfg = RunConfig(output_dir=".")
    run = RunContext(cfg, tmp_path, logger=build_logger(config=LoggingConfig()))
    yield run
    run.prune_old_runs()


@pytest.fixture
def sample_dcp_text():
    return """
name: basic_collect
vendor: mock
steps:
  - id: s1
    command: "show version"
    save: "inventory/version.txt"
  - id: s2
    command: "show alarms"
    save: "inventory/alarms.txt"
"""
