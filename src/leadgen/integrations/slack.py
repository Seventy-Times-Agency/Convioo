import asyncio

import httpx

from leadgen.config import get_settings


async def _send_slack_notification_async(text: str) -> None:
    """Internal async function to send Slack notification."""
    settings = get_settings()
    if not settings.slack_webhook_url:
        return

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                settings.slack_webhook_url,
                json={"text": text},
            )
    except Exception:
        pass


def send_slack_notification(text: str) -> None:
    """Schedule a Slack notification. Non-blocking - returns immediately.

    Safe to call outside an event loop; in that case the work is
    silently dropped.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_send_slack_notification_async(text))
