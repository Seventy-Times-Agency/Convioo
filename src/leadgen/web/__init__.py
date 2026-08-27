"""Deprecated: the aiohttp-based ``/health`` + ``/metrics`` server has
moved to ``leadgen.adapters.web_api``. This module is kept only as a
forwarding alias until every import site has been updated.
"""

from leadgen.adapters.web_api import create_app

__all__ = ["create_app"]
