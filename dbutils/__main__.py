import argparse
import contextlib
import sys
from errno import EINVAL
from pathlib import Path

import alembic.command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from chuni_penguin.calculation import calculate_overpower_base, calculate_play_overpower
from chuni_penguin.calculation.rating import calculate_whole_rating
from chuni_penguin.config import GitSeedsConfig, LocalSeedsConfig, config
from chuni_penguin.database import Chart, PersonalBest
from chuni_penguin.database.base import Base
from chuni_penguin.logging import logger
from chuni_penguin.types import ComboLamp
from chuni_penguin.utils import get_loop_factory

from .aliases import update_aliases
from .chunirec import update_db
from .jackets import update_jackets
from .merge_options import merge_options
from .sdvxin import update_sdvxin
from .seeds import (
    backsync_seeds,
    dump_seeds,
    load_seeds,
    pull_seeds_repository,
    sort_seeds,
    validate_seeds,
)
from .tachi import update_tachi


def add_seeds_repo_arguments(
    parser: argparse.ArgumentParser,
):
    parser.add_argument("-p", "--seeds-path", type=Path, default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--branch", default=None)
    parser.add_argument("--git-username", default=None)
    parser.add_argument("--git-email", default=None)

    return parser


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

    seeds = subparsers.add_parser("seeds", help="Seeds management commands")

    seeds_subparsers = seeds.add_subparsers(dest="seeds_command", required=True)
    add_seeds_repo_arguments(
        seeds_subparsers.add_parser(
            "dump", help="Dump data from the database to seeds files"
        )
    )
    add_seeds_repo_arguments(
        seeds_subparsers.add_parser(
            "load", help="Load data from the seeds files to the database"
        )
    )
    add_seeds_repo_arguments(
        seeds_subparsers.add_parser("check", help="Verify database seeds integrity")
    )
    add_seeds_repo_arguments(
        seeds_subparsers.add_parser("sort", help="Sort database seeds")
    )
    seeds_backsync_parser = add_seeds_repo_arguments(
        seeds_subparsers.add_parser(
            "backsync", help="Backsync database seeds to a Git repository"
        )
    )
    seeds_backsync_parser.add_argument("--git-auth-username", default=None)
    seeds_backsync_parser.add_argument("--git-auth-password", default=None)

    subparsers.add_parser("recalc", help="Performs a recalc of all personal bests")

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

    if args.command == "seeds":
        if (
            args.url is not None
            and args.branch is not None
            and args.git_username is not None
            and args.git_email is not None
        ):
            seeds_config = GitSeedsConfig(
                url=args.url,
                branch=args.branch,
                username=args.git_username,
                email=args.git_email,
            )
        elif args.seeds_path is not None:
            seeds_config = LocalSeedsConfig(args.seeds_path)
        else:
            seeds_config = config.seeds

        seeds_repo = pull_seeds_repository(logger, seeds_config)

        with contextlib.closing(seeds_repo):
            if args.seeds_command == "dump":
                await dump_seeds(
                    logger,
                    async_sessionmaker(engine, expire_on_commit=False),
                    seeds_repo,
                )
            if args.seeds_command == "load":
                await load_seeds(logger, engine, seeds_repo)
            if args.seeds_command == "check":
                await validate_seeds(logger, seeds_repo)
            if args.seeds_command == "sort":
                await sort_seeds(logger, seeds_repo)
            if args.seeds_command == "backsync":
                if not isinstance(seeds_config, GitSeedsConfig):
                    logger.error(
                        "Cannot backsync a local repository.", config=seeds_config
                    )
                    sys.exit(EINVAL)

                await backsync_seeds(
                    logger,
                    async_sessionmaker(engine, expire_on_commit=False),
                    seeds_config,
                    seeds_repo,
                    git_auth_username=args.git_auth_username,
                    git_auth_password=args.git_auth_password,
                )

    if args.command == "recalc":
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

        async with sessionmaker() as session, session.begin():
            query = select(func.count()).select_from(PersonalBest)
            count = (await session.execute(query)).scalar_one()

            logger.info("performing recalc", count=count)

            query = select(PersonalBest, Chart.const).join(
                Chart,
                (Chart.song_id == PersonalBest.song_id)
                & (Chart.difficulty == PersonalBest.difficulty),
            )

            for i, row in enumerate(await session.execute(query)):
                pb, const = row

                if const is None:
                    pb.rating = None
                    pb.overpower = None
                else:
                    pb.rating = calculate_whole_rating(pb.score, const) // 100
                    pb.overpower = int(
                        calculate_play_overpower(
                            calculate_overpower_base(pb.score, const),
                            ComboLamp(pb.combo_lamp),
                        )
                        * 1000
                    )

                session.add(pb)

                if i % 10000 == 0:
                    logger.debug("iterating over database", done=i, total=count)

    await engine.dispose()


if __name__ == "__main__":
    import asyncio

    with asyncio.Runner(loop_factory=get_loop_factory()) as runner:
        runner.run(main())
