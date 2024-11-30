import itertools
from decimal import Decimal
import random
from typing import TYPE_CHECKING, Literal, Optional, Sequence

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context, Range
from discord.utils import escape_markdown
from sqlalchemy import select, text
from sqlalchemy.orm import joinedload

from chunithm_net.models.enums import Rank
from database.models import Chart
from utils import did_you_mean_text, floor_to_ndp, round_to_nearest
from utils.calculation.overpower import (
    calculate_overpower_base,
    calculate_overpower_max,
)
from utils.calculation.rating import calculate_rating, calculate_score_for_rating
from utils.components import ChartCardEmbed
from utils.constants import MAX_DIFFICULTY, SIMILARITY_THRESHOLD

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.autocompleters import AutocompletersCog
    from cogs.botutils import UtilsCog


class ToolsCog(commands.Cog, name="Tools"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = self.bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]
        self.autocompleters: "AutocompletersCog" = self.bot.get_cog("Autocompleters")  # type: ignore[reportGeneralTypeIssues]

    @commands.hybrid_command("anmitsu", aliases=["rub"])
    async def anmitsu(
        self,
        ctx: Context,
        bpm: Range[float, 1, 10000],
        note_density: Range[int, 1, 1024] = 16,
    ):
        """Determine whether you can get JUSTICE / JUSTICE CRITICAL through "anmitsu" technique.

        "Anmitsu" is a technique where when two notes appear on different lanes with slightly different timing, you hit both
        of them at the same time. When the two notes are close enough in timing, they will have a JUSTICE CRITICAL overlap
        duration where you can tap both notes at the exact same time and get JUSTICE CRITICAL for both. The closer the notes,
        the easier it is to perform the "anmitsu" technique. It is said that "anmitsu" technique is ideal when the distance
        between two notes is below 50ms (i.e. the JUSTICE CRITICAL overlap duration is at least 16.67ms).

        Rubbing the ground slider is a technique where when two tap notes appear in the same lane, you rub the ground slider
        instead of tapping the notes individually. If the two notes are close enough in timing, you will not get JUSTICE or
        ATTACK.

        Parameters
        ----------
        bpm: float
            BPM of the song. Use the `info` command to find this.
        note_density: int
            Note value, for example 16 means 1/16 notes (16 notes = 1 measure).
        """

        note_distance_1000 = int(240000 * 1000 / bpm / note_density)
        crit_overlap_1000 = max(66667 - note_distance_1000, 0)
        jus_overlap_1000 = max(133333 - note_distance_1000, 0)
        res = f"At **{bpm}** BPM, the distance between two **1/{note_density}** notes is `{note_distance_1000 // 100 / 10}ms`."
        res += f"\n• The JUSTICE CRITICAL overlap duration is `{crit_overlap_1000 // 100 / 10}ms`"
        res += f"\n• The JUSTICE overlap duration is `{jus_overlap_1000 // 100 / 10}ms`"

        if crit_overlap_1000 > 0:
            res += "\n\n:white_check_mark: If these notes appear vertically, you can rub the ground slider and will not get JUSTICE and below."
        elif jus_overlap_1000 > 0:
            res += "\n\n:warning: If these notes appear vertically and you rub the ground slider, you will not get ATTACK but you might get JUSTICE."
        else:
            res += "\n\n:x: If these notes appear vertically, you might get ATTACK if you rub the ground slider."

        if crit_overlap_1000 > 16667:
            res += '\n:white_check_mark: If these notes appear in different lanes, you can tap both of them at the same time ("anmitsu" technique) and get JUSTICE CRITICAL for both notes during the JUSTICE CRITICAL overlap duration.'
        elif jus_overlap_1000 > 16667:
            res += "\n:warning: If these notes appear in different lanes and you tap both of them at the same time, you are very likely to get JUSTICE or ATTACK therefore it is not recommended."
        else:
            res += "\n:x: If these notes appear in different lanes, you should tap them individually since the notes are too far from each other."

        await ctx.reply(res, mention_author=False)

    @commands.hybrid_command("calculate", aliases=["calc"])
    async def calculate(
        self,
        ctx: Context,
        score: Range[int, 0, 1010000],
        chart_constant: Optional[float] = None,
    ):
        """Calculate rating and over power from score and chart constant.

        Parameters
        ----------
        score: int
            The score to calculate play rating and over power from
        chart_constant: float
            Chart constant of the chart. Use the `info` command to find this.
        """

        if chart_constant is not None and (
            chart_constant < 1 or chart_constant > MAX_DIFFICULTY
        ):
            msg = f"Chart constant must be between 1 and {MAX_DIFFICULTY}."
            raise commands.BadArgument(msg)

        if chart_constant is None:
            rating = calculate_rating(score, 0)
            const_text = ""
        else:
            rating = calculate_rating(score, chart_constant)
            const_text = f" on a chart with chart constant **{chart_constant}**"

        sign = ""
        if chart_constant is None and rating > 0:
            sign = "+"

        res = f"A score of **{score}**{const_text} will give:"
        res += f"\n• Rating: **{sign}{floor_to_ndp(rating, 2)}**"

        if chart_constant is not None:
            overpower_max = calculate_overpower_max(chart_constant)
            overpower_max_floored = floor_to_ndp(overpower_max, 2)

            if score == 1010000:
                res += f"\n• OVER POWER: **{overpower_max_floored} / {overpower_max_floored} (100.00%)**"
            elif score < 500000:
                res += f"\n• OVER POWER: **0.00 / {overpower_max_floored} (0.00%)**"
            else:
                overpower_base = calculate_overpower_base(score, chart_constant)

                res += "\n• OVER POWER:"

                if score >= 1000000:
                    overpower = overpower_base + Decimal(1)
                    overpower_fc_percentage = floor_to_ndp(
                        overpower / overpower_max * 100, 2
                    )
                    res += f"\n▸ AJ: **{floor_to_ndp(overpower, 2)} / {overpower_max_floored} ({overpower_fc_percentage}%)**"

                overpower = overpower_base + Decimal(0.5)
                overpower_fc_percentage = floor_to_ndp(
                    overpower / overpower_max * 100, 2
                )
                overpower_base_percentage = floor_to_ndp(
                    overpower_base / overpower_max * 100, 2
                )

                res += f"\n▸ FC: **{floor_to_ndp(overpower, 2)} / {overpower_max_floored} ({overpower_fc_percentage}%)**"
                res += f"\n▸ Non-FC: **{floor_to_ndp(overpower_base, 2)} / {overpower_max_floored} ({overpower_base_percentage}%)**"

        await ctx.reply(res, mention_author=False)

    @commands.hybrid_command("const", aliases=["constant"])
    async def const(
        self,
        ctx: Context,
        chart_constant: Range[float, 1.0, MAX_DIFFICULTY],
        mode: Literal["default", "aj"] = "default",
    ):
        """Calculate rating and over power achieved with various scores based on chart constant.

        Parameters
        ----------
        chart_constant: float
            Chart constant of the chart. Use the `info` command to find this.
        mode: str
            Sets the display mode: `default` (Display rating information only) / `aj` (Display OP information for ALL JUSTICE only)
        """

        res = f"Calculation for chart constant **{chart_constant}**:"
        if mode == "aj":
            separator = "-------------------------"
            res += f"```  Score |         OP (AJ)\n{separator}"
            scores = [1009950]
            scores.extend(
                itertools.chain(
                    range(1009900, 1009450, -50),  # 1009500..=1009900
                    range(1009400, 1008900, -100),  # 1009000..=1009400
                )
            )
        else:
            separator = "---------------"
            res += f"```  Score |  Rate\n{separator}"
            scores = [1009000]
            scores.extend(
                itertools.chain(
                    range(1008500, 1004500, -500),  # 1005000..=1008500
                    range(1004000, 999000, -1000),  # 1000000..=1004000
                    range(997500, 972500, -2500),  # 975000..=997500
                    range(970000, 940000, -10000),  # 950000..=970000
                    range(925000, 875000, -25000),  # 900000..=925000
                )
            )
        overpower_max = calculate_overpower_max(chart_constant)
        if mode == "aj":
            rating = calculate_rating(1010000, chart_constant)
            res += f"\n1010000 | {overpower_max:>5.2f} = 100.00%"

        for score in scores:
            rating = calculate_rating(score, chart_constant)
            overpower_base = calculate_overpower_base(score, chart_constant)
            if score >= Rank.SS.min_score:
                overpower = overpower_base + Decimal(1)
                overpower_aj = f"{floor_to_ndp(overpower / overpower_max * 100, 2)}%"
            else:
                overpower_aj = "     -"

            if rating > 0:
                res += "\n"
                if mode == "aj":
                    # AJ means scores are above 1m => overpower is defined
                    res += f"{score:>7} | {overpower:>5.2f} = {overpower_aj:>7}"  # type: ignore[reportUnboundVariable]
                else:
                    res += f"{score:>7} | {floor_to_ndp(rating, 2):>5.2f}"
                    if (
                        score == Rank.SSS.min_score
                        or score == Rank.SSp.min_score
                        or score == Rank.SS.min_score
                        or score == Rank.Sp.min_score
                        or score == Rank.S.min_score
                    ):
                        res += f"\n{separator}"

        res += "```"

        await ctx.reply(res, mention_author=False)

    @commands.hybrid_command("rating")
    async def rating(
        self, ctx: Context, rating: Range[float, 1.0, MAX_DIFFICULTY + 2.15]
    ):
        """Calculate score required to achieve the specified play rating.

        Parameters
        ----------
        rating: float
            Play rating you want to achieve
        """

        res = f"Score required to achieve **{rating}** play rating:"
        res += "\n```Const |   Score\n---------------"

        chart_constant_10 = int(rating - 3) * 10
        rating_10 = rating * 10
        max_10 = MAX_DIFFICULTY * 10

        if chart_constant_10 < 1:
            chart_constant_10 = 1
        while chart_constant_10 <= rating_10 and chart_constant_10 <= max_10:
            required_score = calculate_score_for_rating(
                rating_10 / 10, chart_constant_10 / 10
            )

            if required_score is not None and required_score >= Rank.S.min_score:
                res += f"\n {chart_constant_10 / 10:>4.1f} | {int(required_score):>7}"
            if chart_constant_10 >= 100:
                chart_constant_10 += 1
            elif chart_constant_10 >= 70:
                chart_constant_10 += 5
            else:
                chart_constant_10 += 10
        res += "```"

        await ctx.reply(res, mention_author=False)

    @commands.hybrid_command("random")
    async def random(self, ctx: Context, level: str, count: Range[int, 1, 4] = 3):
        """Get random charts based on level or chart constant.

        Parameters
        ----------
        level: str
            Level to search for. Can be level (13+) or chart constant (13.5).
        count: int
            Number of charts to return. Must be between 1 and 4.
        """

        async with ctx.typing(), self.bot.begin_db_session() as session:
            # Check whether input is level or constant
            stmt = (
                select(Chart)
                .order_by(text("RANDOM()"))
                .limit(count)
                .options(joinedload(Chart.song), joinedload(Chart.sdvxin_chart_view))
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

            charts: Sequence[Chart] = (await session.execute(stmt)).scalars().all()

            if len(charts) == 0:
                await ctx.reply("No charts found.", mention_author=False)
                return

            master_song_ids = [
                chart.song.id for chart in charts if chart.difficulty == "MAS"
            ]

            if XL_TECHNO_JUMPSCARE in master_song_ids:
                await ctx.reply(XL_TECHNO_JUMPSCARE, mention_author=False)
                return
            if VOLCANIC_SONG_ID in master_song_ids:
                await ctx.reply(VOLCANIC_JUMPSCARE, mention_author=False)
                return
            if FORSAKEN_TALE_SONG_ID in master_song_ids and random.random() < 0.5:
                await ctx.reply(FORSAKEN_TALE_JUMPSCARE, mention_author=False)
                return

            embeds: list[discord.Embed] = [ChartCardEmbed(chart) for chart in charts]
            await ctx.reply(embeds=embeds, mention_author=False)

    @commands.hybrid_command("recommend")
    async def recommend(
        self,
        ctx: Context,
        count: Range[int, 1, 4] = 3,
        max_rating: Optional[float] = None,
    ):
        """Get random chart recommendations with target scores based on your rating.

        Please note that recommended charts are generated randomly and are independent of your high scores.

        Parameters
        ----------
        count: int
            Number of charts to return. Must be between 1 and 4.
        max_rating: Optional[float]
            Your maximum rating. If not provided, your rating will be fetched from CHUNITHM-NET,
            assuming you're logged in.
        """

        async with ctx.typing(), self.bot.begin_db_session() as session:
            if max_rating is None:
                async with self.utils.chuninet(ctx) as client:
                    basic_player_data = await client.authenticate()
                    max_rating = basic_player_data.rating.max

                    if max_rating is None:
                        msg = "No rating data found. Please play a song first."
                        raise commands.BadArgument(msg)

            # Determine min-max const to recommend based on user rating. Formula is intentionally confusing.
            min_level = max_rating * 1.05 - 3.05
            max_level = max_rating * 0.85 + 0.95
            if min_level < 7:
                min_level = 7
            if max_level < 14:
                max_level += (14 - max_level) * 0.2
            if max_level < min_level + 1:
                max_level = min_level + 1

            stmt = (
                select(Chart)
                .where((Chart.const >= min_level) & (Chart.const <= max_level))
                .order_by(text("RANDOM()"))
                .limit(count)
                .options(joinedload(Chart.song), joinedload(Chart.sdvxin_chart_view))
            )

            charts: Sequence[Chart] = (await session.execute(stmt)).scalars().all()
            if len(charts) == 0:
                await ctx.reply("No charts found.", mention_author=False)
                return

            embeds: list[discord.Embed] = []
            for chart in charts:
                assert chart.const is not None

                target_score = calculate_score_for_rating(max_rating, chart.const)
                if target_score is None:
                    target_score = 1_009_000
                elif 0 <= target_score < 1_000_000:
                    target_score = round_to_nearest(target_score, 5000)
                elif target_score < 1_006_000:
                    target_score = round_to_nearest(target_score, 2500)
                elif target_score < 1_008_500:
                    target_score = round_to_nearest(target_score, 1000)
                elif target_score < 1_009_000:
                    target_score = round_to_nearest(target_score, 500)

                embeds.append(ChartCardEmbed(chart, target_score=target_score))
            await ctx.reply(embeds=embeds, mention_author=False)

    async def song_title_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.autocompleters.song_title_autocomplete(interaction, current)

    @commands.hybrid_command("border")
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name="BASIC", value="BASIC"),
            app_commands.Choice(name="ADVANCED", value="ADVANCED"),
            app_commands.Choice(name="EXPERT", value="EXPERT"),
            app_commands.Choice(name="MASTER", value="MASTER"),
            app_commands.Choice(name="ULTIMA", value="ULTIMA"),
        ]
    )
    @app_commands.autocomplete(query=song_title_autocomplete)
    async def border(self, ctx: Context, difficulty: str, *, query: str):
        """Display the number of permissible JUSTICE, ATTACK and MISS to achieve specific ranks on a chart.

        The values are based on realistic JUSTICE:ATTACK:MISS ratios and are for reference only.
        In terms of scoring, the score decrease from 1 ATTACK is equivalent to 51 JUSTICE, and 1 MISS is equivalent to 101 JUSTICE.

        Parameters
        ----------
        difficulty: str
            Chart difficulty to search for (BAS/ADV/EXP/MAS/ULT).
        query: str
            Song title to search for. You don't have to be exact; try things out!
        """

        async with ctx.typing(), self.bot.begin_db_session() as session:
            guild_id = ctx.guild.id if ctx.guild else None
            song, alias, similarity = await self.utils.find_song(
                query, guild_id=guild_id, worlds_end=False
            )
            if song is None or similarity < SIMILARITY_THRESHOLD:
                return await ctx.reply(
                    did_you_mean_text(song, alias), mention_author=False
                )

            stmt = (
                select(Chart)
                .where(
                    (Chart.song == song) & (Chart.difficulty == difficulty[:3].upper())
                )
                .limit(1)
                .options(joinedload(Chart.song), joinedload(Chart.sdvxin_chart_view))
            )

            chart = (await session.execute(stmt)).scalar_one_or_none()
            if chart is None:
                await ctx.reply(
                    "No charts found. Make sure you specified a valid chart difficulty (BAS/ADV/EXP/MAS/ULT).",
                    mention_author=False,
                )
                return None

            if chart.maxcombo is None:
                await ctx.reply(
                    content=f"We currently don't have note counts for {escape_markdown(song.title)} [{chart.difficulty}]. Calculating the border is not possible. Please try again later.",
                    mention_author=False,
                )
                return None

            await ctx.reply(
                embed=ChartCardEmbed(chart, border=True), mention_author=False
            )
            return None


XL_TECHNO_SONG_ID = 2035
XL_TECHNO_JUMPSCARE = """恐怖！XL TECHNO -More Dance Remix-

           —
—
           —
  —
           —
     —
           —
        —
           —
           —
           —
              —
           —
                 —
           —
                    —
"""  # noqa: RUF001

VOLCANIC_SONG_ID = 625
VOLCANIC_JUMPSCARE = """🟨🟨🟥🟨🟨
🟨🟨🟥🟨🟨
🟨🟨🟥🟨🟨
🟨🟨🟥🟨🟨
🟨🟨🟥🟨🟨    𝓿𝓸𝓵𝓬𝓪𝓷𝓲𝓬
🟨🟨🟥🟨🟨
🟨🟨🟥🟨🟨
🟨🟨🟥🟨🟨 
🟨🟨🟥🟨🟨
"""  # noqa: W291, RUF001

FORSAKEN_TALE_SONG_ID = 2652
FORSAKEN_TALE_JUMPSCARE = """恐怖！Forsaken Tale！
😡     😡     😡
     😡     😡
😡     😡     😡
     😡     😡
          😠
"""  # noqa: RUF001


async def setup(bot: "ChuniBot"):
    await bot.add_cog(ToolsCog(bot))
