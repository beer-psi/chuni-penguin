from types import SimpleNamespace
from typing import TYPE_CHECKING, Sequence

import discord
from discord import Embed, app_commands
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import escape_markdown as emd
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from chunithm_net.models.enums import Difficulty
from database.models import Alias, Chart, Song
from utils import (
    did_you_mean_text,
    get_jacket_url,
    shlex_split,
    yt_search_link,
)
from utils.config import config
from utils.constants import SIMILARITY_THRESHOLD
from utils.views.embeds import EmbedPaginationView
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
            charts: Sequence[Chart] = (await session.execute(stmt)).scalars().all()

            if len(charts) == 0:
                await ctx.reply("No charts found.", mention_author=False)
                return

            view = SonglistView(ctx, charts)
            view.message = await ctx.reply(
                embed=view.format_songlist(view.items[: view.per_page]),
                view=view,
                mention_author=False,
            )

    @commands.hybrid_command("addalias")
    async def addalias(
        self,
        ctx: Context,
        song_title_or_alias: str,
        added_alias: str,
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

        if global_alias and ctx.author.id not in config.bot.alias_managers:
            msg = "You are not allowed to add global aliases."
            raise commands.CheckFailure(msg)

        if global_alias:
            guild_id = -1
        elif ctx.guild is not None:
            guild_id = ctx.guild.id
        else:
            msg = "ctx.guild == None and global_alias == True"
            raise RuntimeError(msg)

        async with ctx.typing(), self.bot.begin_db_session() as session, session.begin():
            stmt = (
                select(Song)
                .where(func.lower(Song.title) == func.lower(added_alias))
                .limit(1)
            )
            song = (await session.execute(stmt)).scalar_one_or_none()

            if song is not None:
                msg = f"**{emd(added_alias)}** is already a song title."
                raise commands.BadArgument(msg)

            if global_alias:
                stmt = (
                    select(Alias)
                    .where(func.lower(Alias.alias) == func.lower(added_alias))
                    .options(joinedload(Alias.song))
                )
                aliases = (await session.execute(stmt)).scalars().all()

                if len(aliases) > 0 and aliases[0].guild_id == -1:
                    msg = f"**{emd(added_alias)}** already exists (global alias for **{emd(aliases[0].song.title)}**)."
                    raise commands.BadArgument(msg)

                if len(aliases) > 0 and aliases[0].guild_id != -1:
                    aliases[0].guild_id = -1
                    aliases[0].owner_id = None
                    await session.merge(aliases[0])

                    for x in aliases[1:]:
                        await session.delete(x)

                    return await ctx.reply(
                        f"**{emd(added_alias)}** already exists as a guild-only alias. Promoting to global alias.",
                        mention_author=False,
                    )
            else:
                stmt = (
                    select(Alias)
                    .where(
                        (func.lower(Alias.alias) == func.lower(added_alias))
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

            stmt = select(Song).where(
                # Limit to non-WE entries. WE entries are redirected to
                # their non-WE respectives when song-searching anyways.
                (func.lower(Song.title) == func.lower(song_title_or_alias))
                & (Song.id < 8000)
            )
            song = (await session.execute(stmt)).scalar_one_or_none()

            if song is None:
                condition = func.lower(Alias.alias) == func.lower(song_title_or_alias)

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

            session.add(
                Alias(
                    alias=added_alias,
                    guild_id=guild_id,
                    song_id=song.id,
                    owner_id=None if global_alias else ctx.author.id,
                )
            )

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
    async def removealias(self, ctx: Context, *, removed_alias: str):
        """Remove an alias for this server.

        Parameters
        ----------
        alias: str
            The alias to remove.
        """

        is_alias_manager = ctx.author.id in config.bot.alias_managers

        if not is_alias_manager and ctx.guild is None:
            raise commands.NoPrivateMessage

        async with ctx.typing(), self.bot.begin_db_session() as session, session.begin():
            condition = func.lower(Alias.alias) == func.lower(removed_alias)

            if not is_alias_manager and ctx.guild is not None:
                condition = condition & (Alias.guild_id == ctx.guild.id)

            stmt = select(Alias).where(condition)
            alias = (await session.execute(stmt)).scalar_one_or_none()

            if alias is None:
                msg = f"**{emd(removed_alias)}** does not exist"

                if not is_alias_manager:
                    msg += " or you don't have permissions to remove it"

                msg += "."

                raise commands.BadArgument(msg)

            if (
                not is_alias_manager
                and alias.guild_id != -1
                and alias.owner_id != ctx.author.id
                and not (
                    isinstance(ctx.author, discord.Member)
                    and ctx.author.guild_permissions.administrator
                )
            ):
                msg = "You cannot delete an alias that you didn't add yourself."
                raise commands.CheckFailure(msg)

            await session.delete(alias)

        await self.utils._reload_alias_cache()
        await ctx.reply(
            f"Removed {'global ' if alias.guild_id == -1 else ''}alias **{emd(removed_alias)}**.",
            mention_author=False,
        )

    @commands.hybrid_command("listalias", aliases=["listaliases", "aliases"])
    async def listalias(self, ctx: Context, *, query: str):
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
    async def info_slash(
        self,
        interaction: "discord.Interaction[ChuniBot]",
        query: str,
        *,
        detailed: bool = False,
    ):
        ctx = await Context.from_interaction(interaction)
        return await self._info_inner(ctx, query=query, detailed=detailed)

    @commands.command("info")
    async def info(self, ctx: Context, *, query: str):
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
        async with ctx.typing(), self.bot.begin_db_session() as session:
            guild_id = ctx.guild.id if ctx.guild is not None else None
            result = await self.utils.find_songs(query, guild_id=guild_id)

            if result.similarity < SIMILARITY_THRESHOLD:
                return await ctx.reply(
                    did_you_mean_text(result.songs[0], result.matched_alias),
                    mention_author=False,
                )

            song_embeds: list[Embed] = []
            verse_chart_constant_notice = False

            for song in result.songs:
                stmt = (
                    select(Chart)
                    .where(Chart.song_id == song.id)
                    .order_by(Chart.id)
                    .options(joinedload(Chart.sdvxin_chart_view))
                )
                charts = (await session.execute(stmt)).scalars().all()

                song_description = ""

                if not song.available:
                    if song.removed:
                        song_description += "**This song is removed.**\n\n"
                    else:
                        song_description += "**This song is not available in CHUNITHM International.**\n\n"

                if (
                    not verse_chart_constant_notice
                    and song.version == "VERSE"
                    and any((x.const is not None and x.const >= 14.7 for x in charts))
                ):
                    verse_chart_constant_notice = True

                displayed_version = song.version
                displayed_bpm = "Unknown"

                if song.release is not None:
                    displayed_version += f" ({song.release})"

                if song.bpm is not None:
                    displayed_bpm = str(song.bpm)

                    if (
                        song.min_bpm is not None
                        and song.max_bpm is not None
                        and song.min_bpm != song.max_bpm
                    ):
                        displayed_bpm = (
                            f"{displayed_bpm} ({song.min_bpm}~{song.max_bpm})"
                        )

                song_description += (
                    f"**Artist**: {emd(song.artist)}\n"
                    f"**Category**: {song.genre}\n"
                    f"**Version**: {displayed_version}\n"
                )

                for chart in charts:
                    if chart.version is not None:
                        difficulty = Difficulty.from_short_form(chart.difficulty)

                        song_description += (
                            f"**Version ({difficulty})**: {chart.version}\n"
                        )

                song_description += f"**BPM**: {displayed_bpm}\n"

                embed = discord.Embed(
                    title=song.title,
                    color=discord.Color.yellow(),
                ).set_thumbnail(url=get_jacket_url(song))

                chart_level_desc = []

                for chart in charts:
                    url = (
                        chart.sdvxin_chart_view.url
                        if chart.sdvxin_chart_view is not None
                        else yt_search_link(song.title, chart.difficulty, chart.level)
                    )

                    if detailed:
                        difficulty = Difficulty.from_short_form(chart.difficulty)

                        link_text = f"Lv.{chart.level}"
                        if chart.const is not None:
                            link_text += f" ({chart.const:.1f})"

                        desc = f"{difficulty.emoji()} [{link_text}]({url})"
                    else:
                        if chart.difficulty == "WE":
                            displayed_difficulty = "WORLD'S END"
                        else:
                            displayed_difficulty = chart.difficulty[0]

                        desc = f"[{displayed_difficulty}]({url}) {chart.level}"

                        if chart.const is not None:
                            desc += f" ({chart.const:.1f})"

                    if detailed and chart.charter is not None:
                        desc += f" Designer: {emd(chart.charter)}"

                    if detailed:
                        maxcombo = chart.maxcombo or "-"
                        tap = chart.tap or "-"
                        hold = chart.hold or "-"
                        slide = chart.slide or "-"
                        air = chart.air or "-"
                        flick = chart.flick or "-"
                        desc += f"\n**{maxcombo}** / {tap} / {hold} / {slide} / {air} / {flick}"
                    chart_level_desc.append(desc)

                if len(chart_level_desc) > 0:
                    song_description += "\n**Level**:\n"
                    if detailed:
                        song_description += (
                            "**CHAIN** / TAP / HOLD / SLIDE / AIR / FLICK\n\n"
                        )
                        song_description += "\n".join(chart_level_desc)
                    else:
                        song_description += " / ".join(chart_level_desc)

                embed.description = song_description
                song_embeds.append(embed)

            content = (
                "Chart constants follow CHUNITHM VERSE's scale."
                if verse_chart_constant_notice
                else None
            )

            view = EmbedPaginationView(ctx, song_embeds)
            view.message = await ctx.reply(
                content=content,
                embed=view.items[0],
                view=view,
                mention_author=False,
            )
            return None


async def setup(bot: "ChuniBot"):
    await bot.add_cog(SearchCog(bot))
