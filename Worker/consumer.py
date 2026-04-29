import asyncio
import json
import logging
from collections import defaultdict

import aio_pika
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
import sys
from pythonjsonlogger import jsonlogger

from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

EXCHANGE_NAME = "clicks"
QUEUE_NAME = "clicks.analytics"
DLQ_NAME = "clicks.analytics.dlq"
CLICK_ROUTING_KEY = "click.recorded"

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)



def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


async def setup_topology(channel) -> aio_pika.Queue:
    """
    Declare all exchanges and queues.
    Topology setup is idempotent — safe to run on every startup.
    """
    # Dead-letter exchange
    dlx = await channel.declare_exchange(
        "clicks.dlx",
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )

    # Dead-letter queue — holds messages that failed after all retries
    dlq = await channel.declare_queue(DLQ_NAME, durable=True)
    await dlq.bind(dlx, routing_key=DLQ_NAME)

    # Main exchange
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )

    # Main queue — wired to DLX so failed messages route there automatically
    queue = await channel.declare_queue(
        QUEUE_NAME,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "clicks.dlx",
            "x-dead-letter-routing-key": DLQ_NAME,
            "x-message-ttl": 86_400_000,  # 24 hours in ms
        },
    )
    await queue.bind(exchange, routing_key=CLICK_ROUTING_KEY)

    return queue


async def flush_batch(batch: dict[str, int]) -> None:
    """
    Write accumulated click counts to Postgres in a single query.
    Uses a single UPDATE with CASE expression — one round trip for N shortcodes.
    """
    
    logger.info(
        "Batch flushed to database",
        extra={
            "event": "batch_flush",
            "shortcode_count": len(batch),
            "total_clicks": sum(batch.values()),
        }
    )
    
    if not batch:
        return

    db = SessionLocal()
    try:
        for shortcode, count in batch.items():
            db.execute(
                text(
                    "UPDATE links SET click_count = click_count + :count "
                    "WHERE shortcode = :shortcode"
                ),
                {"count": count, "shortcode": shortcode},
            )
        db.commit()
        logger.info("Flushed batch: %d shortcodes, %d total clicks", len(batch), sum(batch.values()))
    except Exception as e:
        db.rollback()
        logger.error("Batch flush failed: %s", e)
        raise
    finally:
        db.close()


async def run_consumer() -> None:
    connection = await aio_pika.connect_robust(
        settings.rabbitmq_url,
        reconnect_interval=5,
        fail_fast=False,
    )

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=settings.batch_size)

        queue = await setup_topology(channel)

        # In-memory accumulator: shortcode -> click count
        batch: dict[str, int] = defaultdict(int)
        pending_messages: list = []

        async def process_message(message: aio_pika.IncomingMessage) -> None:
            
            logger.error(
                "Unparseable message routed to DLQ",
                extra={
                    "event": "dlq_route",
                    "body": message.body.decode(errors="replace")[:200],
                }
            )
            
            try:
                payload = json.loads(message.body.decode())
                shortcode = payload["shortcode"]
                batch[shortcode] += 1
                pending_messages.append(message)
            except Exception as e:
                logger.error("Failed to parse message: %s | body: %s", e, message.body)
                await message.reject(requeue=False)  # → DLQ

        async def flush_loop() -> None:
            while True:
                await asyncio.sleep(settings.batch_flush_seconds)
                if pending_messages:
                    current_batch = dict(batch)
                    current_pending = list(pending_messages)
                    batch.clear()
                    pending_messages.clear()

                    try:
                        await flush_batch(current_batch)
                        # Acknowledge all messages in batch after successful DB write
                        for msg in current_pending:
                            await msg.ack()
                    except Exception:
                        # DB write failed — reject all, they go to DLQ
                        for msg in current_pending:
                            await msg.reject(requeue=False)

        async with queue.iterator() as queue_iter:
            flush_task = asyncio.create_task(flush_loop())
            try:
                async for message in queue_iter:
                    await process_message(message)

                    if len(pending_messages) >= settings.batch_size:
                        # Hit batch size limit — flush immediately
                        current_batch = dict(batch)
                        current_pending = list(pending_messages)
                        batch.clear()
                        pending_messages.clear()

                        try:
                            await flush_batch(current_batch)
                            for msg in current_pending:
                                await msg.ack()
                        except Exception:
                            for msg in current_pending:
                                await msg.reject(requeue=False)
            finally:
                flush_task.cancel()