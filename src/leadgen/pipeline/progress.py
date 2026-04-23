"""Progress reporting helper for long-running search tasks.

Throttles Telegram edits so we don't burn through rate limits on every
lead, but still keeps the user informed with a progress bar + ETA.
"""

from __future__ import annotations

import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

BAR_WIDTH = 15
MIN_EDIT_INTERVAL_SEC = 2.5


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def render_bar(done: int, total: int) -> str:
    if total <= 0:
        return "░" * BAR_WIDTH
    ratio = max(0.0, min(1.0, done / total))
    filled = int(round(BAR_WIDTH * ratio))
    return "█" * filled + "░" * (BAR_WIDTH - filled)


class ProgressReporter:
    """Edits a single Telegram message to show phased progress + ETA.

    Call ``phase()`` when switching high-level stage, ``update()`` with
    per-item counts during a long phase. Edits are throttled to avoid
    hitting Telegram's message-edit rate limit.
    """

    def __init__(self, bot: Bot, chat_id: int, message_id: int) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self._started_at = time.monotonic()
        self._phase_started_at = self._started_at
        self._last_edit_at = 0.0
        self._last_text: str | None = None
        self._title = ""
        self._subtitle = ""
        self._force_next_update = True

    async def phase(self, title: str, subtitle: str = "") -> None:
        """Switch to a new phase — text update with no progress bar."""
        self._title = title
        self._subtitle = subtitle
        self._phase_started_at = time.monotonic()
        # Ensure the first progress update after a phase change always renders
        # so the user sees "0/N" bar immediately instead of waiting for the
        # throttle window to expire.
        self._force_next_update = True
        await self._write(title if not subtitle else f"{title}\n<i>{subtitle}</i>")

    async def update(self, done: int, total: int) -> None:
        """Update the progress bar for the current phase."""
        now = time.monotonic()
        # Always render the very end or the first tick after a phase change,
        # otherwise throttle to avoid hitting Telegram's edit-rate ceiling.
        is_terminal = total > 0 and done >= total
        forced = self._force_next_update
        if (
            not is_terminal
            and not forced
            and (now - self._last_edit_at) < MIN_EDIT_INTERVAL_SEC
        ):
            return
        self._force_next_update = False

        phase_elapsed = now - self._phase_started_at
        if done <= 0:
            eta_str = "~вычисляю"
        else:
            remaining = phase_elapsed * (total - done) / done
            eta_str = f"~{_format_elapsed(remaining)}"

        bar = render_bar(done, total)
        text = (
            f"{self._title}\n"
            f"<i>{self._subtitle}</i>\n\n"
            f"<code>[{bar}] {done}/{total}</code>\n"
            f"прошло {_format_elapsed(phase_elapsed)} · осталось {eta_str}"
        )
        await self._write(text)

    async def finish(self, text: str) -> None:
        """Replace the progress message with a final text."""
        await self._write(text, force=True)

    async def _write(self, text: str, *, force: bool = False) -> None:
        if not force and text == self._last_text:
            return
        try:
            await self.bot.edit_message_text(
                text,
                chat_id=self.chat_id,
                message_id=self.message_id,
            )
            self._last_text = text
            self._last_edit_at = time.monotonic()
        except TelegramBadRequest as exc:
            # Message might be unchanged (same text) or too old — benign.
            if "message is not modified" not in str(exc).lower():
                logger.debug("progress edit failed: %s", exc)
        except Exception:  # noqa: BLE001
            logger.exception("progress edit unexpectedly failed")
