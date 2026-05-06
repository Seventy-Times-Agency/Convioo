import httpx

from src.leadgen.config import get_settings


async def send_slack_notification(text: str) -> None:
    """Send a notification to Slack if webhook URL is configured.

    Silently handles failures if Slack is unavailable.
    """
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
