import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import check_api_key
from app.db import get_session
from app.models import Outbox, Payment, PaymentStatus
from app.schemas import PaymentCreate, PaymentCreated, PaymentOut

router = APIRouter(prefix="/api/v1/payments", dependencies=[Depends(check_api_key)])


def as_created(payment: Payment) -> PaymentCreated:
    return PaymentCreated(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


def as_details(payment: Payment) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.meta or {},
        status=payment.status,
        idempotency_key=payment.idempotency_key,
        webhook_url=payment.webhook_url,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )


@router.post("", status_code=202, response_model=PaymentCreated)
async def create_payment(
    body: PaymentCreate,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    if not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="Пустой Idempotency-Key")

    existing = await session.scalar(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )
    if existing:
        return as_created(existing)

    payment_id = uuid.uuid4()
    payment = Payment(
        id=payment_id,
        amount=body.amount,
        currency=body.currency.value,
        description=body.description,
        meta=body.metadata,
        status=PaymentStatus.pending.value,
        idempotency_key=idempotency_key,
        webhook_url=str(body.webhook_url),
    )
    session.add(payment)
    session.add(Outbox(payload={"payment_id": str(payment_id)}))

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        return as_created(existing)

    return as_created(payment)


@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(
    payment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")

    return as_details(payment)
