import asyncio
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractRobustConnection

from energy_agent.core.config import Settings

MessageHandler = Callable[[AbstractIncomingMessage], Awaitable[None]]


class RabbitMQProvider:
    provider_type = "real"
    routing_key = "energy.indexing.job.v1"
    retry_routing_key = "energy.indexing.retry.v1"
    dead_routing_key = "energy.indexing.dead.v1"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.connection: AbstractRobustConnection | None = None
        self.channel: AbstractChannel | None = None

    async def connect(self) -> None:
        self.connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        channel = await self.connection.channel(publisher_confirms=True)
        self.channel = channel
        await channel.set_qos(prefetch_count=self.settings.rabbitmq_prefetch_count)
        await self.declare_topology()

    async def declare_topology(self) -> None:
        if not self.channel:
            raise RuntimeError("RABBITMQ_UNAVAILABLE")
        exchange = await self.channel.declare_exchange(
            self.settings.rabbitmq_index_exchange,
            ExchangeType.DIRECT,
            durable=True,
        )
        main = await self.channel.declare_queue(
            self.settings.rabbitmq_index_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": self.settings.rabbitmq_index_exchange,
                "x-dead-letter-routing-key": self.dead_routing_key,
            },
        )
        retry = await self.channel.declare_queue(
            self.settings.rabbitmq_index_retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": self.settings.rabbitmq_retry_delay_ms,
                "x-dead-letter-exchange": self.settings.rabbitmq_index_exchange,
                "x-dead-letter-routing-key": self.routing_key,
            },
        )
        dead = await self.channel.declare_queue(
            self.settings.rabbitmq_index_dead_queue,
            durable=True,
        )
        await main.bind(exchange, self.routing_key)
        await retry.bind(exchange, self.retry_routing_key)
        await dead.bind(exchange, self.dead_routing_key)

    async def publish(self, payload: bytes, *, routing_key: str | None = None) -> None:
        if not self.channel:
            raise RuntimeError("RABBITMQ_UNAVAILABLE")
        exchange = await self.channel.get_exchange(self.settings.rabbitmq_index_exchange)
        message = Message(
            payload,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
        )
        async with asyncio.timeout(self.settings.rabbitmq_publish_timeout_seconds):
            confirmed = await exchange.publish(
                message,
                routing_key=routing_key or self.routing_key,
                mandatory=True,
            )
        if confirmed is None:
            raise RuntimeError("RABBITMQ_PUBLISH_TIMEOUT")

    async def consume(self, handler: MessageHandler) -> None:
        if not self.channel:
            raise RuntimeError("RABBITMQ_UNAVAILABLE")
        queue = await self.channel.get_queue(self.settings.rabbitmq_index_queue)
        await queue.consume(handler, no_ack=False)

    async def close(self) -> None:
        if self.connection:
            await self.connection.close()
