"""Tests for the in-process progress broker used by the SSE endpoint."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from leadgen.core.services import (
    BrokerProgressSink,
    ProgressBroker,
    ProgressEvent,
)


@pytest.mark.asyncio
async def test_publish_reaches_single_subscriber() -> None:
    broker = ProgressBroker()
    sid = uuid.uuid4()

    async def collect() -> list[ProgressEvent]:
        out: list[ProgressEvent] = []
        async for event in broker.subscribe(sid):
            out.append(event)
        return out

    task = asyncio.create_task(collect())
    # Let the subscriber register before we publish.
    await asyncio.sleep(0)

    await broker.publish(sid, ProgressEvent("phase", {"title": "t"}))
    await broker.publish(sid, ProgressEvent("update", {"done": 1, "total": 10}))
    await broker.close(sid)

    events = await asyncio.wait_for(task, timeout=1)
    kinds = [e.kind for e in events]
    assert kinds == ["phase", "update"]


@pytest.mark.asyncio
async def test_two_subscribers_both_receive() -> None:
    broker = ProgressBroker()
    sid = uuid.uuid4()

    async def collect() -> list[ProgressEvent]:
        out: list[ProgressEvent] = []
        async for event in broker.subscribe(sid):
            out.append(event)
        return out

    a = asyncio.create_task(collect())
    b = asyncio.create_task(collect())
    await asyncio.sleep(0)

    await broker.publish(sid, ProgressEvent("phase", {"title": "one"}))
    await broker.close(sid)

    ra, rb = await asyncio.wait_for(asyncio.gather(a, b), timeout=1)
    assert len(ra) == 1
    assert len(rb) == 1
    assert ra[0].kind == rb[0].kind == "phase"


@pytest.mark.asyncio
async def test_broker_sink_publishes_all_three_kinds() -> None:
    broker = ProgressBroker()
    sid = uuid.uuid4()

    async def collect() -> list[str]:
        out: list[str] = []
        async for event in broker.subscribe(sid):
            out.append(event.kind)
        return out

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    sink = BrokerProgressSink(broker, sid)
    await sink.phase("discovery")
    await sink.update(3, 10)
    await sink.finish("done")  # also closes the subscription

    kinds = await asyncio.wait_for(task, timeout=1)
    assert kinds == ["phase", "update", "finish"]


@pytest.mark.asyncio
async def test_unknown_id_publish_is_noop() -> None:
    broker = ProgressBroker()
    # No subscriber → must not raise.
    await broker.publish(uuid.uuid4(), ProgressEvent("phase", {"t": "x"}))
