import logging
from pathlib import Path

from fncollect.logging_setup import RedactionFilter


def test_redaction_filter_removes_secrets():
    filt = RedactionFilter(["supersecret"])
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname=__file__, lineno=1,
        msg="password is supersecret and token", args=(), exc_info=None,
    )
    assert filt.filter(record) is True
    assert "supersecret" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_run_context_writes_manifest_and_artifact(run_ctx, tmp_path):
    path = run_ctx.write_text(
        Path("inventory"), "version.txt", "mock device", "dcp"
    )
    assert path.exists()
    manifest = run_ctx.finalize({"vendor": "mock"})
    assert manifest.exists()
    text = manifest.read_text()
    assert "version.txt" in text
    assert "sha256" in text


def test_run_context_sanitizes_names():
    from fncollect.session_ctx import sanitize

    assert sanitize("a b/c!d") == "a_b_c_d"


def test_session_log_per_session_type(run_ctx):
    run_ctx.append_session_log("cmd-a", "out-a", session="cli")
    run_ctx.append_session_log("cmd-b", "out-b", session="tnd")
    run_ctx.append_session_log("cmd-c", "out-c", session=None)  # generic
    assert (run_ctx.dir / "device_session_cli.log").exists()
    assert (run_ctx.dir / "device_session_tnd.log").exists()
    assert (run_ctx.dir / "device_session.log").exists()
    cli = (run_ctx.dir / "device_session_cli.log").read_text()
    assert ">>> cmd-a" in cli and "out-a" in cli and "[status 0]" in cli
