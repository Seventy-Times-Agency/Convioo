"""FastAPI surface for the web frontend (Vercel-hosted Next.js).

Health, metrics, auth, search start/list/status, SSE progress, full
CRM endpoints (leads, templates, tasks, activity, custom fields),
team management, GDPR export/delete, and Excel/CSV export. The only
delivery surface for the product since the Telegram bot was removed.
"""

from leadgen.adapters.web_api.app import create_app

__all__ = ["create_app"]
