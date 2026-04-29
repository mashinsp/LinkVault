import json
import logging
from datetime import datetime, timezone

import aio_pika
from aio_pika.abc import AbstractRobustConnection

from config import settings

logger = logging.getLogger(__name__)

_connection: AbstractRobustConnection | None = None
_channel = None

EXCHANGE_NAME = "clicks"
CLICK_ROUTING_KEY = "click.recorded"


async def get_connection() -> AbstractRobustConnection:
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(
            settings.rabbitmq_url,
            reconnect_interval=5,
        )
    return _connection


async def get_channel():
    global _channel
    connection = await get_connection()
    if _channel is None or _channel.is_closed:
        _channel = await connection.channel()
        await _channel.set_qos(prefetch_count=100)

        # Declare exchange — idempotent, safe to call on every startup
        await _channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
    return _channel


async def publish_click_event(shortcode: str, user_agent: str | None, ip: str | None) -> None:
    """
    Fire-and-forget: publish a click event to RabbitMQ.
    If publishing fails, we log and continue — a missed click count
    is acceptable. A failed redirect is not.
    """
    try:
        channel = await get_channel()
        exchange = await channel.get_exchange(EXCHANGE_NAME)

        payload = {
            "shortcode": shortcode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent,
            "ip": ip,
        }

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
            ),
            routing_key=CLICK_ROUTING_KEY,
        )
    except Exception as e:
        logger.warning("Failed to publish click event for %s: %s", shortcode, e)


async def close_connection() -> None:
    global _connection
    if _connection and not _connection.is_closed:
        await _connection.close()