"""Thin client-specific layers on top of ``core``.

Each sub-package plugs core services into one delivery surface:
- ``web_api`` — FastAPI endpoints + SSE (the only adapter today)

Adapters know about their framework. ``core`` never does.
"""
