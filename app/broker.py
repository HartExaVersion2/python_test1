from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings

broker = RabbitBroker(settings.rabbit_url)

payments_exchange = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
dlx = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

new_queue = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key="payments.new",
)

dlq = RabbitQueue(
    "payments.dlq",
    durable=True,
    routing_key="payments.dlq",
)


def retry_queue(number, ttl_ms):
    name = f"payments.retry.{number}"
    return RabbitQueue(
        name,
        durable=True,
        routing_key=name,
        arguments={
            "x-message-ttl": ttl_ms,
            "x-dead-letter-exchange": "payments",
            "x-dead-letter-routing-key": "payments.new",
        },
    )


retry_queues = (
    retry_queue(1, 1000),
    retry_queue(2, 2000),
    retry_queue(3, 4000),
)


async def declare_topology():
    payments = await broker.declare_exchange(payments_exchange)
    dead = await broker.declare_exchange(dlx)

    queue = await broker.declare_queue(new_queue)
    await queue.bind(payments, routing_key="payments.new")

    for item in retry_queues:
        declared = await broker.declare_queue(item)
        await declared.bind(dead, routing_key=item.name)

    dead_queue = await broker.declare_queue(dlq)
    await dead_queue.bind(dead, routing_key="payments.dlq")
