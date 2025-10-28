import contextlib
import hashlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Annotated, override

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import escape_markdown as emd
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from chuni_penguin.config import config
from chuni_penguin.constants import SIMILARITY_THRESHOLD
from chuni_penguin.context import PenguinContext
from chuni_penguin.converters import (
    AliasNameConverter,
    AliasNameTransformer,
    Level,
    LevelRange,
    LevelRangeConverter,
)
from chuni_penguin.database import Alias, Chart, Course, Song
from chuni_penguin.logging import logged_app_command, logged_prefix_command
from chuni_penguin.networks.errors import NetworkError
from chuni_penguin.networks.types import CourseRecord
from chuni_penguin.ui import (
    ConfirmationYesView,
    CourseListView,
    SongInfoPaginationView,
    SonglistView,
)
from chuni_penguin.utils import did_you_mean_text, shlex_split

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot
    from chuni_penguin.cogs.autocompleters import AutocompletersCog
    from chuni_penguin.cogs.botutils import UtilsCog


class SearchCog(commands.Cog, name="Search"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]
        self.autocompleters: "AutocompletersCog" = bot.get_cog("Autocompleters")  # type: ignore[reportGeneralTypeIssues]

    @override
    async def cog_load(self) -> None:
        hoist_commands = [
            (self.addalias, ("addalias",)),
            (self.removealias, ("removealias",)),
            (self.listalias, ("listalias", "listaliases", "aliases")),
            (self.reloadalias, ("reloadalias",)),
        ]

        for command, name_and_aliases in hoist_commands:
            name, *aliases = name_and_aliases

            new_command = command.copy()
            new_command.name = name
            new_command.parent = None
            new_command.cog = self
            new_command.hidden = True

            if len(aliases) > 0:
                new_command.aliases = aliases

            new_command.app_command = None

            self.bot.add_command(new_command)

    async def _song_title_autocomplete(
        self,
        interaction: "discord.Interaction[ChuniBot]",
        current: str,
    ):
        return await self.autocompleters.song_title_autocomplete(interaction, current)

    @commands.hybrid_command("find")
    @logged_prefix_command
    async def find(
        self,
        ctx: Context,
        level: Annotated[Level | LevelRange, LevelRangeConverter],
    ):
        """Find charts by level or chart constant.

        Parameters
        ----------
        level: Level | LevelRange
            Level (13+), chart constant (13.5), or level range (13.2-13.7) to search for.
        """

        stmt = (
            select(Chart)
            .options(joinedload(Chart.sdvxin_chart_view), joinedload(Chart.song))
            .join(Song, Chart.song)
            .order_by(Chart.const, Song.title)
        )

        if isinstance(level, LevelRange):
            if level.min_level is not None:
                stmt = stmt.where(
                    Chart.const
                    >= (level.min_level.const or level.min_level.inferred_const)
                )

            if level.max_level is not None:
                stmt = stmt.where(
                    Chart.const
                    <= (level.max_level.const or level.max_level.inferred_max_const)
                )
        elif level.const is not None:
            stmt = stmt.where(Chart.const == level.const)
        else:
            stmt = stmt.where(Chart.level == level.level)

        async with ctx.typing(), self.bot.begin_db_session() as session:
            charts = (await session.execute(stmt)).scalars().all()

            if len(charts) == 0:
                await ctx.reply("No charts found.", mention_author=False)
                return

            view = SonglistView(ctx, list(charts))
            await view.start()

    @commands.hybrid_group("alias")
    @logged_prefix_command
    async def alias(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @alias.command("add")
    @app_commands.autocomplete(song_title_or_alias=_song_title_autocomplete)
    @logged_prefix_command
    async def addalias(
        self,
        ctx: Context,
        song_title_or_alias: Annotated[str, AliasNameConverter],
        added_alias: Annotated[str, AliasNameConverter],
        *,
        global_alias: bool = False,
    ):
        """Manually add a song alias for this server.

        Aliases are case-insensitive.

        Parameters
        ----------
        song_title_or_alias: str
            The title (or an existing alias) of the song.
        added_alias: str
            The alias to add.
        global_alias: bool
            Whether to apply the alias globally. Only a few users can do this.

        Examples
        --------
        addalias Titania tritania
        addalias "祈 -我ら神祖と共に歩む者なり-" prayer
        """

        # this command is guild-only
        if not global_alias and ctx.guild is None:
            raise commands.NoPrivateMessage

        is_alias_manager = (
            ctx.author.id in config.bot.alias_managers
            or ctx.author.id == self.bot.owner_id
        )

        if global_alias and not is_alias_manager:
            msg = "You are not allowed to add global aliases."
            raise commands.CheckFailure(msg)

        source_alias_lower = song_title_or_alias.lower()
        added_alias_lower = added_alias.lower()

        if global_alias:
            guild_id = -1
        elif ctx.guild is not None:
            guild_id = ctx.guild.id
        else:
            msg = "ctx.guild == None and global_alias == True"
            raise RuntimeError(msg)

        async with (
            ctx.typing(),
            self.bot.begin_db_session() as session,
            session.begin(),
        ):
            stmt = (
                select(Song).where(func.lower(Song.title) == added_alias_lower).limit(1)
            )
            song = (await session.execute(stmt)).scalar_one_or_none()

            if song is not None:
                msg = f"**{emd(added_alias)}** is already a song title."
                raise commands.BadArgument(msg)

            stmt = select(Song).where(
                # Limit to non-WE entries. WE entries are redirected to
                # their non-WE respectives when song-searching anyways.
                (func.lower(Song.title) == source_alias_lower) & (Song.id < 8000)
            )
            song = (await session.execute(stmt)).scalar_one_or_none()

            if song is None:
                condition = func.lower(Alias.alias) == source_alias_lower

                if not global_alias:
                    condition = condition & (
                        (Alias.guild_id == -1) | (Alias.guild_id == guild_id)
                    )

                stmt = select(Alias).where(condition).options(joinedload(Alias.song))
                alias_unit = (await session.execute(stmt)).scalar_one_or_none()

                if alias_unit is None:
                    msg = f"**{emd(song_title_or_alias)}** does not exist."
                    raise commands.BadArgument(msg)

                song = alias_unit.song

            if global_alias:
                stmt = (
                    select(Alias)
                    .where(func.lower(Alias.alias) == added_alias_lower)
                    .options(joinedload(Alias.song))
                )
                aliases = (await session.execute(stmt)).scalars().all()

                if len(aliases) > 0 and aliases[0].guild_id == -1:
                    msg = f"**{emd(added_alias)}** already exists (global alias for **{emd(aliases[0].song.title)}**)."
                    raise commands.BadArgument(msg)

                if len(aliases) > 0 and aliases[0].guild_id != -1:
                    aliases[0].guild_id = -1
                    aliases[0].owner_id = None
                    aliases[0].song_id = song.id
                    await session.merge(aliases[0])

                    for x in aliases[1:]:
                        await session.delete(x)

                    await session.commit()
                    await self.utils._reload_alias_cache()
                    return await ctx.reply(
                        f"**{emd(added_alias)}** already exists as a guild-only alias. Promoting to global alias.",
                        mention_author=False,
                    )
            else:
                stmt = (
                    select(Alias)
                    .where(
                        (func.lower(Alias.alias) == added_alias_lower)
                        & ((Alias.guild_id == -1) | (Alias.guild_id == guild_id))
                    )
                    .options(joinedload(Alias.song))
                )
                alias_unit = (await session.execute(stmt)).scalar_one_or_none()

                if alias_unit is not None:
                    msg = (
                        f"**{emd(added_alias)}** already exists "
                        f"({'global ' if alias_unit.guild_id == -1 else ''}alias for **{emd(alias_unit.song.title)}**)."
                    )
                    raise commands.BadArgument(msg)

            session.add(
                Alias(
                    alias=added_alias,
                    guild_id=guild_id,
                    song_id=song.id,
                    owner_id=None if global_alias else ctx.author.id,
                )
            )
            await session.commit()

        await self.utils._reload_alias_cache()

        alias_unit = "an alias" if not global_alias else "a global alias"

        await ctx.reply(
            f"Added **{emd(added_alias)}** as {alias_unit} for **{emd(song_title_or_alias)}**.",
            mention_author=False,
        )

        return None

    @alias.command("remove", aliases=["delete"])
    @logged_prefix_command
    async def removealias(
        self,
        ctx: Context,
        *,
        removed_alias: Annotated[str, AliasNameConverter],
    ):
        """Remove an alias for this server.

        The alias owner can always delete their own aliases. If someone
        has the Manage Server permissions then they can also delete it.

        Parameters
        ----------
        alias: str
            The alias to remove.
        """

        is_alias_manager = (
            ctx.author.id in config.bot.alias_managers
            or ctx.author.id == self.bot.owner_id
        )

        if not is_alias_manager and ctx.guild is None:
            raise commands.NoPrivateMessage

        # If the person is not an alias manager, we already know that this
        # command must be run in a guild.
        bypass_ownership_check: bool = (
            is_alias_manager or ctx.author.guild_permissions.manage_guild  # pyright: ignore[reportAttributeAccessIssue]
        )

        async with (
            ctx.typing(),
            self.bot.begin_db_session() as session,
            session.begin(),
        ):
            condition = func.lower(Alias.alias) == removed_alias.lower()

            if is_alias_manager:
                guild_condition = Alias.guild_id == -1

                if ctx.guild is not None:
                    guild_condition |= Alias.guild_id == ctx.guild.id

                condition &= guild_condition
            elif ctx.guild is not None:
                condition &= Alias.guild_id == ctx.guild.id

            if not bypass_ownership_check:
                condition &= Alias.owner_id == ctx.author.id

            stmt = select(Alias).where(condition)

            # when searching for guild_id = ctx.guild.id or guild_id = -1, the cases that happen are
            # - it is a global alias, in which case there is only *the* global alias
            # - it is a guild alias, in which case the global alias doesn't exist
            # therefore there should be only one or no aliases
            alias = (await session.execute(stmt)).scalar_one_or_none()

            if alias is None:
                msg = f"**{emd(removed_alias)}** does not exist"

                if not bypass_ownership_check:
                    msg += " or you don't have permissions to remove it"

                msg += "."

                raise commands.CommandError(msg)

            # if there is a suitable alias, then we can definitely remove it, since we
            # have already matched all of the conditions above.
            await session.delete(alias)
            await session.commit()

        await self.utils._reload_alias_cache()
        await ctx.reply(
            f"Removed {'global ' if alias.guild_id == -1 else ''}alias **{emd(removed_alias)}**.",
            mention_author=False,
        )

    @alias.command("list")
    @logged_prefix_command
    async def listalias(
        self, ctx: Context, *, query: Annotated[str, AliasNameConverter(lower=True)]
    ):
        """List aliases for a given song

        Parameters
        ----------
        query: str
            The song to get aliases for. You don't have to be exact; this works
            the same way as `c>info`.
        """
        guild_id = ctx.guild.id if ctx.guild is not None else None
        song, alias, similarity = await self.utils.find_song(query, guild_id=guild_id)

        if song is None:
            await ctx.reply(
                did_you_mean_text(ctx.clean_prefix, song, alias), mention_author=False
            )
            return

        if similarity < SIMILARITY_THRESHOLD:
            view = ConfirmationYesView(ctx)

            await view.start(content=did_you_mean_text(ctx.clean_prefix, song, alias))
            await view.wait()

            if not view.result:
                return

        async with self.bot.begin_db_session() as session:
            stmt = select(Alias).where(Alias.song_id == song.id)
            aliases = (await session.execute(stmt)).scalars().all()

        embed = discord.Embed(
            title=f"Aliases for {song.title}",
            color=discord.Color.yellow(),
        )
        embed.description = ""
        global_aliases = [x.alias for x in aliases if x.guild_id == -1]

        if len(global_aliases) > 0:
            embed.description += (
                "**Global aliases:**\n"
                f"{', '.join([x.alias for x in aliases if x.guild_id == -1])}"
            )

        if ctx.guild is not None:
            local_aliases = [x.alias for x in aliases if x.guild_id == ctx.guild.id]

            if len(local_aliases) > 0:
                embed.description += (
                    "\n\n"
                    "**Local aliases:**\n"
                    f"{', '.join([x.alias for x in aliases if x.guild_id == ctx.guild.id])}"
                )

        embed.description = embed.description.strip()

        await ctx.reply(embed=embed, mention_author=False)

    @alias.command("reload", with_app_command=False, hidden=True)
    @commands.is_owner()
    @logged_prefix_command
    async def reloadalias(self, ctx: Context):
        async with ctx.typing():
            await self.utils._reload_alias_cache()

            alias_count = sum([len(x) for x in self.utils.alias_cache.values()])

            await ctx.reply(
                content=f"Loaded {alias_count} aliases into memory.",
                mention_author=False,
            )

    @app_commands.command(name="info", description="Search for a song.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        query="Song title to search for. You don't have to be exact; try things out!",
        detailed="Display detailed chart information (note counts and designer name)",
    )
    @app_commands.autocomplete(query=_song_title_autocomplete)
    @logged_app_command
    async def info_slash(
        self,
        interaction: "discord.Interaction[ChuniBot]",
        query: app_commands.Transform[str, AliasNameTransformer(lower=True)],
        *,
        detailed: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)
        return await self._info_inner(ctx, query=query, detailed=detailed)

    @commands.command("info", usage="[-d] <query>")
    @logged_prefix_command
    async def info(
        self,
        ctx: PenguinContext,
        *,
        query: Annotated[str, AliasNameConverter(lower=True)],
    ):
        """Search for a song.

        **Parameters:**
        `query`: Song title to search for. You don't have to be exact; try things out!
        `-d`: Show detailed info, such as note counts and charter.
        """
        args = SimpleNamespace(detailed=False, query=[])

        argv = shlex_split(query)
        for arg in argv:
            if arg in ["-d", "--detailed"]:
                args.detailed = True
            else:
                args.query.append(arg)

        query = " ".join(args.query)
        return await self._info_inner(ctx, query=query, detailed=args.detailed)

    async def _info_inner(
        self, ctx: PenguinContext, *, query: str, detailed: bool = False
    ):
        async with ctx.typing():
            guild_id = ctx.guild.id if ctx.guild is not None else None
            result = await self.utils.find_songs(
                query, guild_id=guild_id, load_global_aliases=True
            )

            if result.similarity < SIMILARITY_THRESHOLD:
                view = ConfirmationYesView(ctx)

                await view.start(
                    content=did_you_mean_text(
                        ctx.clean_prefix, result.songs[0], result.matched_alias
                    )
                )
                await view.wait()

                if not view.result:
                    return

            if query == "67" and any(song.id == 45 for song in result.songs):
                await ctx.bot.database.user_found_easter_egg(
                    ctx.author.id, "L9-upside-down-is-67"
                )

            view = SongInfoPaginationView(
                ctx,
                result.songs,
                detailed=detailed,
                synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
                brainrot=query == "67",
            )
            await view.start()

            # straight up jorking it
            if (
                ctx.guild is not None
                and hashlib.md5(f"{ctx.guild.id}{query.lower()}".encode()).hexdigest()
                == "9729fe8bdc6e25a045f8c8028e19aa79"
            ):
                await ctx.send(
                    content="https://cdn.discordapp.com/attachments/1348088922055512197/1358215134937612338/vlc-record-2025-04-05-19h01m28s-2025-04-05_18-57-05.mkv-.mp4"
                )

    @commands.hybrid_command("courses")
    @logged_prefix_command
    async def courses(self, ctx: PenguinContext):
        """Get a list of all courses.

        If you are logged in to CHUNITHM-NET, this also displays your course records.
        """

        async with ctx.typing():
            # This is mainly an informative command, so we don't wanna stress too hard
            # that the user isn't logged in.
            course_records: list[CourseRecord] = []

            async with ctx.bot.chunithm_networks.network(ctx) as client:
                if client.SUPPORTS_COURSE_RECORDS:
                    with contextlib.suppress(NetworkError):
                        course_records = await client.get_course_records()

            async with self.bot.begin_db_session() as session:
                # course IDs are prefixed by version, so 25xxx is sun plus, 30xxx is luminous,
                # and so on. really convenient
                query = select(Course.version).distinct().order_by(Course.id)
                versions = (await session.execute(query)).scalars().all()

        if len(versions) == 0:
            msg = "No course data."
            raise commands.CommandError(msg)

        view = CourseListView(ctx, versions, course_records)
        await view.start()


async def setup(bot: "ChuniBot"):
    await bot.add_cog(SearchCog(bot))
