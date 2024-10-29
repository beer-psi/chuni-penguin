# ruff: noqa: RUF001

import argparse
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from database.models import Base
from utils.config import config
from utils.evtloop import get_event_loop
from utils.logging import setup_logging

from .aliases import update_aliases
from .chunirec import update_db
from .jackets import update_jackets
from .merge_options import merge_options
from .sdvxin import update_sdvxin

setup_logging("dbutils")
logger = logging.getLogger("dbutils")


async def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        title="subcommands", dest="command", required=True
    )

    subparsers.add_parser("create", help="Initializes the database")

    update = subparsers.add_parser(
        "update", help="Fill the database with data from various sources"
    )
    update.add_argument(
        "source", choices=["chunirec", "sdvxin", "jackets", "alias", "dump"]
    )
    update.add_argument(
        "--data-dir",
        required=False,
        type=Path,
        help="If updating from data, provide path to the `data` folder.",
    )
    update.add_argument(
        "--option-dir",
        required=False,
        type=Path,
        help="If updating from data, provide path to the `option` folder.",
    )

    args = parser.parse_args()

    engine: AsyncEngine = create_async_engine(
        config.bot.db_connection_string,
        # Should be ridiculous even for multi-threading
        connect_args={"timeout": 20},
    )

    if args.command == "create":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    if args.command == "update":
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        if args.source == "chunirec":
            await update_db(logger, async_session)
        if args.source == "jackets":
            await update_jackets(logger, async_session)
        if args.source == "sdvxin":
            await update_sdvxin(logger, async_session)
        if args.source == "alias":
            await update_aliases(logger, async_session)
        if args.source == "dump":
            if args.data_dir is None:
                update.print_help()
                exit(1)

            await merge_options(logger, async_session, args.data_dir, args.option_dir)

    await engine.dispose()


if __name__ == "__main__":
    import asyncio
    import sys

    event_loop_impl, loop_factory = get_event_loop()

    if sys.version_info >= (3, 11):
        with asyncio.Runner(loop_factory=loop_factory) as runner:
            runner.run(main())
    else:
        if event_loop_impl is not None:
            event_loop_impl.install()
        asyncio.run(main())
