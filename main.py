import argparse
import asyncio

from app.agent.manus import Manus
from app.logger import logger


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run Manus agent with a prompt")
    parser.add_argument(
        "--prompt", type=str, required=False, help="Input prompt for the agent"
    )
    # sandbox flag: --sandbox to force enable, --no-sandbox to force disable
    parser.add_argument(
        "--sandbox",
        dest="use_sandbox",
        action="store_true",
        help="Enable sandbox mode (overrides config)",
    )
    parser.add_argument(
        "--no-sandbox",
        dest="use_sandbox",
        action="store_false",
        help="Disable sandbox mode (overrides config)",
    )
    parser.set_defaults(use_sandbox=None)
    args = parser.parse_args()

    # Apply sandbox CLI override if provided (None means no override)
    if args.use_sandbox is not None:
        try:
            # Import here to avoid circular imports at module import time
            from app.config import config

            # mutate loaded config sandbox setting
            config._config.sandbox.use_sandbox = args.use_sandbox  # type: ignore
        except Exception:
            # If config isn't accessible, ignore and let default behave as before
            pass

    # Create and initialize Manus agent
    agent = await Manus.create()
    try:
        # Use command line prompt if provided, otherwise ask for input
        prompt = args.prompt if args.prompt else input("Enter your prompt: ")
        if not prompt.strip():
            logger.warning("Empty prompt provided.")
            return

        logger.warning("Processing your request...")
        await agent.run(prompt)
        logger.info("Request processing completed.")
    except KeyboardInterrupt:
        logger.warning("Operation interrupted.")
    finally:
        # Ensure agent resources are cleaned up before exiting
        await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
