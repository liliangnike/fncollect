
from fncollect.config import ToolConfig, deep_merge


def test_deep_merge_nested_override():
    base = {"run": {"retention": {"enabled": True, "keep_days": 30}}, "vendor": "mock"}
    override = {"run": {"retention": {"keep_days": 7}}}
    merged = deep_merge(base, override)
    assert merged["run"]["retention"]["enabled"] is True
    assert merged["run"]["retention"]["keep_days"] == 7


def test_load_from_missing_path_uses_defaults(tmp_path):
    config = ToolConfig.load(tmp_path / "nonexistent.yml")
    assert config.vendor == "mock"
    assert config.logging.level == "INFO"


def test_load_merges_local_over_defaults(tmp_path):
    default = tmp_path / "default.yml"
    default.write_text("vendor: nokia_fx\nrun:\n  output_dir: out\n")
    config = ToolConfig.load_defaults([default])
    assert config.vendor == "nokia_fx"
    assert config.run.output_dir == "out"
    assert config.concurrency.max_parallel_devices == 4
