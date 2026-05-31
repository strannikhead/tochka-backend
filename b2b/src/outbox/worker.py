import asyncio
import json
import os
from datetime import UTC, datetime

import aio_pika
from aio_pika import ExchangeType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from b2b.src.db import SessionLocal
from b2b.src.models import OutboxEvent

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://rabbitmq:5672/")
POLL_INTERVAL = float(os.getenv("OUTBOX_POLL_INTERVAL", "1.0"))


async def _publish_events(connection: aio_pika.RobustConnection, session: AsyncSession) -> int:
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .with_for_update(skip_locked=True)
        .limit(100)
    )
    result = await session.execute(stmt)
    events = result.scalars().all()
    if not events:
        return 0

    channel = await connection.channel()
    exchange = await channel.declare_exchange("outbox", ExchangeType.FANOUT, durable=True)

    for ev in events:
        body = json.dumps(ev.payload).encode()
        message = aio_pika.Message(
            body,
            message_id=str(ev.id),
            content_type="application/json",
        )
        await exchange.publish(message, routing_key="")
        ev.published_at = datetime.now(UTC)

    await session.commit()
    await channel.close()
    return len(events)


async def run() -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    try:
        while True:
            async with SessionLocal() as session:  # type: AsyncSession
                try:
                    published = await _publish_events(connection, session)
                except Exception:
                    await session.rollback()
                    raise
            if published == 0:
                await asyncio.sleep(POLL_INTERVAL)

    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(run())
