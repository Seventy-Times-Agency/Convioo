import asyncio
import logging
import sys
import traceback


def _configure_logging() -> None:
    """Configure logging to stdout BEFORE any import that might log.

    Railway reliably captures stdout; this guarantees we see every startup
    line even if a later module fails to import or crashes before the bot
    code sets up its own handlers.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def main() -> None:
    _configure_logging()
    logger = logging.getLogger("leadgen.__main__")

    # Paranoid print — if this doesn't show up in Railway logs, the Python
    # interpreter itself never started (bad Docker CMD, missing package, etc.)
    print("=" * 60, flush=True)
    print(" LEADGEN BOT: Python process starting", flush=True)
    print(f" Python: {sys.version.split()[0]}", flush=True)
    print("=" * 60, flush=True)

    try:
        from leadgen.bot.main import run

        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down")
    except Exception:
        logger.critical("Bot crashed at top level", exc_info=True)
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        raise


if __name__ == "__main__":
    main()
