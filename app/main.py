import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.broker import broker, declare_topology
from app.outbox import relay
from app.payments import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await broker.connect()
    await declare_topology()
    task = asyncio.create_task(relay())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await broker.stop()


app = FastAPI(title="Payments", lifespan=lifespan)
app.include_router(router)
