from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.models import Currency


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: Currency
    description: str
    metadata: dict = Field(default_factory=dict)
    webhook_url: HttpUrl


class PaymentCreated(BaseModel):
    payment_id: UUID
    status: str
    created_at: datetime


class PaymentOut(BaseModel):
    id: UUID
    amount: Decimal
    currency: str
    description: str
    metadata: dict
    status: str
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None
