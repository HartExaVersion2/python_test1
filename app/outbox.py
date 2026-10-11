import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.broker import broker, payments_exchange
from app.db import Session
from app.models import Outbox

log = logging.getLogger("payments.outbox")


async def publish_pending():
    async with Session() as session:
        rows = (
            await session.scalars(
                select(Outbox)
                .where(Outbox.published_at.is_(None))
                .order_by(Outbox.created_at)
                .limit(20)
                .with_for_update(skip_locked=True)
            )
        ).all()

        if not rows:
            return

        for row in rows:
            await broker.publish(
                row.payload,
                exchange=payments_exchange,
                routing_key="payments.new",
                headers={"x-attempt": 0},
                persist=True,
            )
            row.published_at = datetime.now(timezone.utc)

        await session.commit()


async def relay():
    while True:
        try:
            await publish_pending()
        except Exception:
            log.exception("не удалось опубликовать outbox")
        await asyncio.sleep(1)
