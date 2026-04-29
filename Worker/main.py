import asyncio
import logging

from consumer import run_consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Worker starting...")
    await run_consumer()


if __name__ == "__main__":
    asyncio.run(main())