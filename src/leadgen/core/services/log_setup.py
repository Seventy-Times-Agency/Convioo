"""Structlog-based logging setup.

We keep stdlib's ``logging`` API (``logger = logging.getLogger(...)``;
``logger.info("...", arg, arg)``) so no call site changes — structlog
only takes over the *formatting* via ``ProcessorFormatter``. Output
mode is picked by ``LOG_FORMAT``:

- ``json`` (production) — one JSON object per line. Railway and
  external log shippers parse it without regex tricks.
- ``text`` (local dev, default) — coloured one-liners with positional
  args interpolated.

Call ``configure_logging()`` once at process start (entrypoints do
this in ``_configure_logging``); calling again is a cheap no-op.
"""

from __future__ import annotations

import logging
import os
import sys

import structlog

_CONFIGURED = False


def configure_logging(
    *, level: str = "INFO", fmt: str | None = None
) -> None:
    """Wire stdlib logging through structlog's ProcessorFormatter.

    Idempotent: safe to call from both ``__main__`` and the arq worker
    boot path without doubling handlers.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    chosen_fmt = (fmt or os.environ.get("LOG_FORMAT") or "text").lower()
    use_json = chosen_fmt == "json"

    # Shared processor chain: positional-args interpolation, log level
    # name, ISO-8601 timestamp. Renderer is the last step and differs
    # by output mode.
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # Positional-args expansion + the shared chain run on every
        # foreign (non-structlog) record so existing
        # ``logger.info("did %s", thing)`` lines render correctly.
        foreign_pre_chain=[
            structlog.stdlib.ExtraAdder(),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.add_log_level,
            _interpolate_positional_args,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Replace any handlers — structlog's formatter is the source of
    # truth from now on. Avoids double-emission when a previous
    # ``logging.basicConfig`` set its own.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            *shared_processors[2:],  # everything after add_log_level
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def _interpolate_positional_args(
    logger: logging.Logger, name: str, event_dict: dict
) -> dict:
    """Render ``logger.info("hello %s", name)`` into the final string.

    structlog's ProcessorFormatter receives the raw ``msg`` + ``args``
    pair from stdlib. Without this processor JSON output keeps the
    unsubstituted ``%s`` and a separate ``positional_args`` field.
    """
    msg = event_dict.get("event")
    args = event_dict.pop("positional_args", None) or event_dict.pop(
        "args", None
    )
    if args and isinstance(msg, str):
        try:
            event_dict["event"] = msg % args
        except (TypeError, ValueError):
            event_dict["event"] = msg
            event_dict["positional_args"] = list(args)
    return event_dict
