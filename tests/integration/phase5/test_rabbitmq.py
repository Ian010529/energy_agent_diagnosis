from uuid import uuid4

import pytest

from energy_agent.core.config import Settings
from energy_agent.providers.rabbitmq import RabbitMQProvider

pytestmark = pytest.mark.integration


def _settings() -> Settings:
    suffix = uuid4().hex[:10]
    return Settings(
        app_env="test",
        index_execution_mode="rabbitmq",
        rabbitmq_index_exchange=f"energy.indexing.test.{suffix}",
        rabbitmq_index_queue=f"energy.indexing.jobs.test.{suffix}",
        rabbitmq_index_retry_queue=f"energy.indexing.retry.test.{suffix}",
        rabbitmq_index_dead_queue=f"energy.indexing.dead.test.{suffix}",
        rabbitmq_retry_delay_ms=200,
    )


@pytest.mark.asyncio
async def test_rabbitmq_durable_publish_confirm_manual_ack_retry_and_dead_queue() -> None:
    settings = _settings()
    provider = RabbitMQProvider(settings)
    await provider.connect()
    assert provider.channel is not None
    try:
        await provider.publish(b'{"message":"main"}')
        main = await provider.channel.get_queue(settings.rabbitmq_index_queue)
        message = await main.get(no_ack=False, fail=False)
        assert message is not None
        assert message.body == b'{"message":"main"}'
        assert not message.processed
        await message.ack()
        assert message.processed

        await provider.publish(
            b'{"message":"retry"}',
            routing_key=provider.retry_routing_key,
        )
        import asyncio

        await asyncio.sleep(0.5)
        retried = await main.get(no_ack=False, fail=False)
        assert retried is not None
        assert retried.body == b'{"message":"retry"}'
        await retried.ack()

        await provider.publish(
            b'{"message":"dead"}',
            routing_key=provider.dead_routing_key,
        )
        dead = await provider.channel.get_queue(settings.rabbitmq_index_dead_queue)
        dead_message = await dead.get(no_ack=False, fail=False)
        assert dead_message is not None
        await dead_message.ack()
    finally:
        await provider.channel.queue_delete(settings.rabbitmq_index_queue)
        await provider.channel.queue_delete(settings.rabbitmq_index_retry_queue)
        await provider.channel.queue_delete(settings.rabbitmq_index_dead_queue)
        await provider.channel.exchange_delete(settings.rabbitmq_index_exchange)
        await provider.close()
