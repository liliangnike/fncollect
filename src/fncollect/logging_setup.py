"""Logging setup for fncollect.

Provides a logger writing to console and/or a rolling file under the run
directory. Credentials and other sensitive values are redacted before they
ever reach a sink, so the tool can be used (and its logs published) safely.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fncollect.config import LoggingConfig


class RedactionFilter(logging.Filter):
    """Redact configured secrets from any log record's message."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._patterns = [re.compile(re.escape(s)) for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        if self._patterns:
            msg = record.getMessage()
            for pattern in self._patterns:
                msg = pattern.sub("[REDACTED]", msg)
            record.msg = msg
            record.args = ()
        return True


def build_logger(
    name: str = "fncollect",
    config: LoggingConfig | None = None,
    run_dir: Path | None = None,
    extra_secrets: list[str] | None = None,
) -> logging.Logger:
    config = config or LoggingConfig()
    logger = logging.getLogger(name)
    logger.setLevel(config.level.upper())
    logger.handlers.clear()
    logger.propagate = False

    secrets: list[str] = list(config.redact) + (extra_secrets or [])
    redactor = RedactionFilter(secrets)

    if config.console:
        console = logging.StreamHandler()
        console.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
        )
        console.addFilter(redactor)
        logger.addHandler(console)

    if config.file and run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            run_dir / "app.log",
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
            )
        )
        file_handler.addFilter(redactor)
        logger.addHandler(file_handler)

    return logger
