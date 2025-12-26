#!/usr/bin/env python3
"""RQ Worker script for processing generation tasks.

Usage:
    python worker.py

Or with custom queue:
    python worker.py --queue high
"""

import argparse
import logging
import sys

from redis import Redis
from rq import Worker, Queue

from bot.config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for RQ worker."""
    parser = argparse.ArgumentParser(description="RQ Worker for Telegram AI Image Bot")
    parser.add_argument(
        "--queue",
        "-q",
        default="default",
        help="Queue name to listen on (default: default)",
    )
    parser.add_argument(
        "--burst",
        "-b",
        action="store_true",
        help="Run in burst mode (exit when queue is empty)",
    )
    args = parser.parse_args()
    
    # Connect to Redis
    redis_conn = Redis.from_url(config.redis_url)
    logger.info(f"Connected to Redis at {config.redis_url}")
    
    # Create queue
    queue = Queue(name=args.queue, connection=redis_conn)
    logger.info(f"Listening on queue: {args.queue}")
    
    # Start worker
    worker = Worker([queue], connection=redis_conn)
    
    logger.info("Starting RQ worker...")
    worker.work(burst=args.burst)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        sys.exit(1)
