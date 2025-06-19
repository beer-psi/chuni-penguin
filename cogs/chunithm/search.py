import hashlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Annotated

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import escape_markdown as emd
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from database.models import Alias, Chart, Song
from utils import (
    did_you_mean_text,
    shlex_split,
)
from utils.config import config
from utils.constants import SIMILARITY_THRESHOLD
from utils.converters import AliasNameConverter, AliasNameTransformer
from utils.logging import logged_app_command, logged_prefix_command
from utils.views.song_info import SongInfoPaginationView
from utils.views.songlist import SonglistView

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.autocompleters import AutocompletersCog
    from cogs.botutils import UtilsCog


class SearchCog(commands.Cog, name="Search"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]
        self.autocompleters: "AutocompletersCog" = bot.get_cog("Autocompleters")  # type: ignore[reportGeneralTypeIssues]

    @commands.hybrid_command("find")
    @logged_prefix_command
    async def find(self, ctx: Context, level: str):
        """Find charts by level or chart constant.

        Parameters
        ----------
        query: float
            Chart constant to search for.
        """

        stmt = (
            select(Chart)
            .options(joinedload(Chart.sdvxin_chart_view), joinedload(Chart.song))
            .join(Song, Chart.song)
            .order_by(Song.title)
        )

        try:
            if "." in level:
                query_level = float(level)
                stmt = stmt.where(Chart.const == query_level)
            else:
                stmt = stmt.where(Chart.level == level)
        except ValueError:
            msg = "Please enter a valid level or chart constant."
            raise commands.BadArgument(msg) from None

        async with ctx.typing(), self.bot.begin_db_session() as session:
            charts = (await session.execute(stmt)).scalars().all()

            if len(charts) == 0:
                await ctx.reply("No charts found.", mention_author=False)
                return

            view = SonglistView(ctx, list(charts))
            await view.start()

    @commands.hybrid_command("addalias")
    @logged_prefix_command
    async def addalias(
        self,
        ctx: Context,
        song_title_or_alias: Annotated[str, AliasNameConverter(lower=True)],
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
                (func.lower(Song.title) == song_title_or_alias) & (Song.id < 8000)
            )
            song = (await session.execute(stmt)).scalar_one_or_none()

            if song is None:
                condition = func.lower(Alias.alias) == song_title_or_alias

                if not global_alias:
                    condition = condition & (
                        (Alias.guild_id == -1) | (Alias.guild_id == guild_id)
                    )

                stmt = select(Alias).where(condition).options(joinedload(Alias.song))
                alias = (await session.execute(stmt)).scalar_one_or_none()

                if alias is None:
                    msg = f"**{emd(song_title_or_alias)}** does not exist."
                    raise commands.BadArgument(msg)

                song = alias.song

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
                alias = (await session.execute(stmt)).scalar_one_or_none()

                if alias is not None:
                    msg = (
                        f"**{emd(added_alias)}** already exists "
                        f"({'global ' if alias.guild_id == -1 else ''}alias for **{emd(alias.song.title)}**)."
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

        alias = "an alias"
        if global_alias:
            alias = "a global alias"

        await ctx.reply(
            f"Added **{emd(added_alias)}** as {alias} for **{emd(song_title_or_alias)}**.",
            mention_author=False,
        )
        return None

    @commands.hybrid_command("removealias")
    @logged_prefix_command
    async def removealias(
        self,
        ctx: Context,
        *,
        removed_alias: Annotated[str, AliasNameConverter(lower=True)],
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
            condition = func.lower(Alias.alias) == removed_alias

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

    @commands.hybrid_command("listalias", aliases=["listaliases", "aliases"])
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

        if song is None or similarity < SIMILARITY_THRESHOLD:
            return await ctx.reply(did_you_mean_text(song, alias), mention_author=False)

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

        return None

    @commands.is_owner()
    @commands.command("reloadalias", aliases=["reloadaliases"], hidden=True)
    @logged_prefix_command
    async def reloadalias(self, ctx: Context):
        async with ctx.typing():
            await self.utils._reload_alias_cache()

            await ctx.reply(
                content=f"Loaded {len(self.utils.alias_cache)} aliases into memory.",
                mention_author=False,
            )

    async def song_title_autocomplete(
        self,
        interaction: "discord.Interaction[ChuniBot]",
        current: str,
    ):
        return await self.autocompleters.song_title_autocomplete(interaction, current)

    @app_commands.command(name="info", description="Search for a song.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        query="Song title to search for. You don't have to be exact; try things out!",
        detailed="Display detailed chart information (note counts and designer name)",
    )
    @app_commands.autocomplete(query=song_title_autocomplete)
    @logged_app_command
    async def info_slash(
        self,
        interaction: "discord.Interaction[ChuniBot]",
        query: app_commands.Transform[str, AliasNameTransformer(lower=True)],
        *,
        detailed: bool = False,
    ):
        ctx = await Context.from_interaction(interaction)
        return await self._info_inner(ctx, query=query, detailed=detailed)

    @commands.command("info")
    @logged_prefix_command
    async def info(
        self, ctx: Context, *, query: Annotated[str, AliasNameConverter(lower=True)]
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

    async def _info_inner(self, ctx: Context, *, query: str, detailed: bool = False):
        async with ctx.typing():
            guild_id = ctx.guild.id if ctx.guild is not None else None
            result = await self.utils.find_songs(
                query, guild_id=guild_id, load_global_aliases=True
            )

            if result.similarity < SIMILARITY_THRESHOLD:
                return await ctx.reply(
                    did_you_mean_text(result.songs[0], result.matched_alias),
                    mention_author=False,
                )

            view = SongInfoPaginationView(ctx, result.songs, detailed=detailed)
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

            return None


async def setup(bot: "ChuniBot"):
    await bot.add_cog(SearchCog(bot))
