"""Optional arq-backed job queue.

Stage-2 prep: when ``REDIS_URL`` is set, ``enqueue_search`` pushes the
job onto Redis and returns an arq ``Job`` handle; callers resume the
flow asynchronously. When it's unset the helper falls back to
``asyncio.create_task`` so the Telegram bot keeps working on Railway
without Redis wired up yet.

The actual worker side lives in ``leadgen.queue.worker`` — it only
spins up under ``arq leadgen.queue.worker.WorkerSettings``.
"""

from leadgen.queue.enqueue import enqueue_search, is_queue_enabled

__all__ = ["enqueue_search", "is_queue_enabled"]
