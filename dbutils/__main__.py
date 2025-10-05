import argparse
from pathlib import Path

import alembic.command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from chuni_penguin.config import config
from chuni_penguin.database.models import Base
from chuni_penguin.logging import logger
from chuni_penguin.utils import get_loop_factory

from .aliases import update_aliases
from .chunirec import update_db
from .jackets import update_jackets
from .merge_options import merge_options
from .sdvxin import update_sdvxin
from .tachi import update_tachi


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
        "source", choices=["chunirec", "sdvxin", "jackets", "alias", "dump", "tachi"]
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
    update.add_argument(
        "--extract-jackets",
        action="store_true",
        help="If updating from data, extract song jackets to assets/jackets/",
    )
    update.add_argument(
        "--extract-audio",
        action="store_true",
        help="If updating from data, extract song jackets to assets/audio/",
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

        alembic_config = Config(Path(__file__).parent.parent / "alembic.ini")
        alembic.command.stamp(alembic_config, "head")

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
        if args.source == "tachi":
            await update_tachi(logger, async_session)
        if args.source == "dump":
            if args.data_dir is None:
                update.print_help()
                exit(1)

            await merge_options(
                logger,
                async_session,
                args.data_dir,
                args.option_dir,
                extract_jackets=args.extract_jackets,
                extract_audios=args.extract_audio,
            )

    await engine.dispose()


if __name__ == "__main__":
    import asyncio

    with asyncio.Runner(loop_factory=get_loop_factory()) as runner:
        runner.run(main())
