import asyncio
import logging
import random
from datetime import datetime, timezone
from uuid import UUID

import httpx
from faststream import FastStream
from faststream.rabbit import RabbitMessage
from sqlalchemy import update

from app.broker import broker, declare_topology, dlx, new_queue, payments_exchange
from app.db import Session
from app.models import Payment, PaymentStatus

log = logging.getLogger("payments.consumer")

app = FastStream(broker)

MAX_ATTEMPTS = 3


@app.after_startup
async def setup():
    await declare_topology()


async def process_payment(payment_id: str):
    pid = UUID(payment_id)

    async with Session() as session:
        payment = await session.get(Payment, pid)
        if payment is None:
            return None

        status = payment.status
        webhook_url = payment.webhook_url
        amount = payment.amount
        currency = payment.currency

    if status == PaymentStatus.pending.value:
        await asyncio.sleep(random.uniform(2, 5))

        if random.random() < 0.9:
            status = PaymentStatus.succeeded.value
        else:
            status = PaymentStatus.failed.value

        async with Session() as session:
            result = await session.execute(
                update(Payment)
                .where(Payment.id == pid, Payment.status == PaymentStatus.pending.value)
                .values(status=status, processed_at=datetime.now(timezone.utc))
            )
            await session.commit()

            if result.rowcount == 0:
                fresh = await session.get(Payment, pid)
                if fresh is None:
                    return None
                status = fresh.status

    payload = {
        "payment_id": payment_id,
        "status": status,
        "amount": str(amount),
        "currency": currency,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()

    return status


async def park_failed(body, attempt):
    nxt = attempt + 1
    headers = {"x-attempt": nxt}

    if nxt > MAX_ATTEMPTS:
        log.warning("сообщение уходит в dlq, попытка %s", nxt)
        await broker.publish(
            body,
            exchange=dlx,
            routing_key="payments.dlq",
            headers=headers,
            persist=True,
        )
        return

    log.warning("повтор %s через очередь payments.retry.%s", nxt, nxt)
    await broker.publish(
        body,
        exchange=dlx,
        routing_key=f"payments.retry.{nxt}",
        headers=headers,
        persist=True,
    )


@broker.subscriber(new_queue, payments_exchange)
async def on_payment(body: dict, msg: RabbitMessage):
    attempt = 0
    payment_id = None

    try:
        raw = msg.headers.get("x-attempt") or 0
        attempt = int(raw)
        payment_id = body.get("payment_id")
        if not payment_id:
            raise ValueError("в сообщении нет payment_id")
        status = await process_payment(payment_id)
    except Exception:
        log.exception("платёж %s не обработан", payment_id)
        await park_failed(body, attempt)
        return

    if status is None:
        log.warning("платёж %s не найден, сообщение пропускаю", payment_id)
        return

    log.info("платёж %s -> %s", payment_id, status)
