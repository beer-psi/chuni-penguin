# ruff: noqa: RUF003
import asyncio
import itertools
import random
from decimal import Decimal
from io import BytesIO
from typing import TYPE_CHECKING, Annotated, Literal, Optional, Sequence

import discord
import httpx
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context, Range
from discord.utils import escape_markdown
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.orm import joinedload

from chunithm_net.consts import KEY_PLAY_RATING
from chunithm_net.models.enums import Difficulty, Rank
from database.models import Chart, Song
from utils import (
    floor_to_ndp,
    json_loads,
    round_to_nearest,
    sdvxin_link,
    yt_search_link,
)
from utils.border import calculate_border, calculate_score_deduction_per_judgement
from utils.calculation.overpower import (
    calculate_overpower_base,
    calculate_overpower_max,
)
from utils.calculation.rating import calculate_rating, calculate_score_for_rating
from utils.components import ChartCardEmbed
from utils.constants import MAX_DIFFICULTY
from utils.context import PenguinContext
from utils.converters import AliasNameConverter, DifficultyConverter
from utils.kamaitachi import convert_kt_pbs_to_records
from utils.logging import logged_prefix_command, logger
from utils.ranks import rank_icon

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.autocompleters import AutocompletersCog


def compose_chart_view(bg: bytes, data: bytes, bar: bytes):
    with (
        Image.open(BytesIO(bg)) as bg_img,
        Image.open(BytesIO(data)) as data_img,
        Image.open(BytesIO(bar)) as bar_img,
    ):
        if bg_img.mode != "RGBA":
            bg_img = bg_img.convert("RGBA")

        if data_img.mode != "RGBA":
            data_img = data_img.convert("RGBA")

        if bar_img.mode != "RGBA":
            bar_img = bar_img.convert("RGBA")

        background = Image.new("RGBA", bg_img.size, (0, 0, 0, 255))
        result = Image.alpha_composite(background, bg_img)

        if data_img.size != bg_img.size:
            container = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
            container.paste(data_img, (0, 0), data_img)
            data_img = container

        result = Image.alpha_composite(result, data_img)

        if bar_img.size != bg_img.size:
            container = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
            container.paste(bar_img, (0, 0), bar_img)
            bar_img = container

        result = Image.alpha_composite(result, bar_img)

        output = BytesIO()
        result.convert("RGB").save(output, format="JPEG", quality=92)

    output.seek(0)

    return output


class ToolsCog(commands.Cog, name="Tools"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils = self.bot.utils
        self.autocompleters: "AutocompletersCog" = self.bot.get_cog("Autocompleters")  # type: ignore[reportGeneralTypeIssues]

    @commands.hybrid_command("anmitsu", aliases=["rub"])
    @logged_prefix_command
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
        res += f"\n- The JUSTICE CRITICAL overlap duration is `{crit_overlap_1000 // 100 / 10}ms`"
        res += f"\n- The JUSTICE overlap duration is `{jus_overlap_1000 // 100 / 10}ms`"

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
    @logged_prefix_command
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

        if chart_constant is None and score < 900000:
            res = "Rating calculation for scores below 900,000 is dependent on chart constant."
            res += "\nPlease specify chart constant to view detailed calculations."
            # (You really should just git gud though)
            await ctx.reply(res, mention_author=False)
            return

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
        res += f"\n- Rating: **{sign}{floor_to_ndp(rating, 2)}**"

        if chart_constant is not None:
            overpower_max = calculate_overpower_max(chart_constant)
            overpower_max_floored = floor_to_ndp(overpower_max, 2)

            if score == 1010000:
                res += f"\n- OVER POWER: **{overpower_max_floored} / {overpower_max_floored} (100.00%)**"
            elif score < 500000:
                res += f"\n- OVER POWER: **0.00 / {overpower_max_floored} (0.00%)**"
            else:
                overpower_base = calculate_overpower_base(score, chart_constant)

                res += "\n- OVER POWER:"

                if score >= 1000000:
                    overpower = overpower_base + Decimal(1)
                    overpower_fc_percentage = floor_to_ndp(
                        overpower / overpower_max * 100, 2
                    )
                    res += f"\n  - AJ: **{floor_to_ndp(overpower, 2)} / {overpower_max_floored} ({overpower_fc_percentage}%)**"

                overpower = overpower_base + Decimal("0.5")
                overpower_fc_percentage = floor_to_ndp(
                    overpower / overpower_max * 100, 2
                )
                overpower_base_percentage = floor_to_ndp(
                    overpower_base / overpower_max * 100, 2
                )

                res += f"\n  - FC: **{floor_to_ndp(overpower, 2)} / {overpower_max_floored} ({overpower_fc_percentage}%)**"
                res += f"\n  - Non-FC: **{floor_to_ndp(overpower_base, 2)} / {overpower_max_floored} ({overpower_base_percentage}%)**"

        await ctx.reply(res, mention_author=False)

    @commands.hybrid_command("const", aliases=["constant"])
    @logged_prefix_command
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

        chart_constant = round(chart_constant, 2)
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
    @logged_prefix_command
    async def rating(
        self, ctx: Context, rating: Range[float, 1.0, round(MAX_DIFFICULTY + 2.15, 2)]
    ):
        """Calculate score required to achieve the specified play rating.

        Parameters
        ----------
        rating: float
            Play rating you want to achieve
        """

        rating = round(rating, 2)
        res = f"Score required to achieve **{rating:.2f}** play rating:"
        res += "\n```Const |   Score\n---------------"

        chart_constant_10 = int(rating - 3) * 10
        rating_10 = rating * 10
        max_10 = MAX_DIFFICULTY * 10

        if chart_constant_10 < 10:
            chart_constant_10 = 10
        while chart_constant_10 <= rating_10 and chart_constant_10 <= max_10:
            required_score = calculate_score_for_rating(
                round(rating_10 / 10, 2), round(chart_constant_10 / 10, 1)
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
    @logged_prefix_command
    async def random(
        self, ctx: PenguinContext, level: str, count: Range[int, 1, 10] = 3
    ):
        """Get random charts based on level/course/chart constant.

        Parameters
        ----------
        level: str
            Level to search for. Can be a level (13+), a chart constant (13.5), or a
            course class (`i`, `ii`, `iii`, `iv`, `v`, `inf`, `random`, `wallpanic`).
        count: int
            Number of charts to return. Must be between 1 and 10. Not respected when
            rolling a random course.
        """

        course_levels: dict[str, list[str | None]] = {
            "i": ["10", "10+", "11"],
            "ii": ["11+", "12", "12+"],
            "iii": ["12+", "13", "13+"],
            "iv": ["13+", "14", "14+"],
            "sibyl": [None, None, None],
            "v": ["14", "14+", "15"],
            "inf": ["14+", "15", "15+"],
            "random": [None, None, None],
            "wallpanic": ["10+", "11", "11+"],
        }
        sibyl_songs: list[list[int]] = [
            [
                850,  # 《混乱》 ～ Muspell
                851,  # 《理想》 ～ Cloudland
                852,  # 《逃避》 ～ The Deserter
                853,  # 《最愛》 ～ Curse
                1029,  # 《狂乱》 ～ Cataclysm
                1031,  # 《信仰》 ～ Eudaimonia
                2091,  # 《紀律》 ～ As One
                2092,  # 《種子》 ～ Set You Free
                2458,  # 《楽土》 ～ One and Only One
                2459,  # 《散華》 ～ EMBARK
            ],
            [
                854,  # 《運命》 ～ Ray of Hope
                1030,  # 《投影》 ～ Oh My Baby Doll
                1032,  # 《選別》 ～ Refuge
                1033,  # 《本能》 ～ ReCoda
                2090,  # 《偏愛》 ～ Shattered Memories
                2093,  # 《自戒》 ～ Paganelope
                2457,  # 《真紅》 ～ Pavane Pour La Flamme
                2460,  # 《慈雨》 ～ La Symphonie de Salacia: Agony Movement
            ],
            [
                918,  # 《破滅》 ～ Rhapsody for The End
                2461,  # 《創造》 ～ Cries, beyond The End
            ],
        ]
        course_condition: dict[str, str] = {
            "i": "CLASS I: 50 LIFE, MISS -1, CLEAR +10",
            "ii": "CLASS II: 50 LIFE, MISS -1",
            "iii": "CLASS III: 30 LIFE, MISS -1",
            "iv": "CLASS IV: 500 LIFE, JUSTICE or lower -1",
            "sibyl": "CLASS IV - シビュラ精霊記 Random Set: 100 LIFE, ATTACK or lower -1",
            "v": "CLASS V: 300 LIFE, JUSTICE or lower -1",
            "inf": "CLASS ∞: 200 LIFE, JUSTICE or lower -1",
            "random": "CLASS EXTRA - RANDOM: 50 LIFE, MISS -1",
            "wallpanic": "CLASS EXTRA - Wall Panic!: 400 LIFE, JUSTICE or lower -1, JUSTICE CRITICAL +1, field wall gets further back as LIFE decreases",
        }

        async with ctx.typing(), self.bot.begin_db_session() as session:
            stmt = (
                select(Chart)
                .join(Song, Chart.song_id == Song.id)
                .where(Song.removed == False)  # noqa: E712
                .order_by(text("RANDOM()"))
                .options(joinedload(Chart.song), joinedload(Chart.sdvxin_chart_view))
            )

            charts: Sequence[Chart]
            course_mode = level.lower() in course_levels or level.lower() == "infinite"

            if course_mode:
                charts = []
                course_class = level.lower()

                if course_class == "infinite":
                    course_class = "inf"

                content = course_condition[course_class]
                track_levels = course_levels[course_class]

                for i, track_level in enumerate(track_levels):
                    chart_stmt = stmt.limit(1)

                    if track_level is not None:
                        chart_stmt = chart_stmt.where(Chart.level == track_level)
                    elif course_class == "random":
                        chart_stmt = chart_stmt.where(
                            (Chart.song_id >= 8244) & (Chart.song_id <= 8249)
                        )
                    elif course_class == "sibyl":
                        chart_stmt = chart_stmt.where(
                            Chart.song_id.in_(sibyl_songs[i]) & (Chart.difficulty == "MAS")
                        )  # fmt: skip

                    chart = (await session.execute(chart_stmt)).scalar_one_or_none()

                    if chart is not None:
                        charts.append(chart)
            else:
                content = None
                try:
                    if "." in level:
                        query_level = float(level)
                        stmt = stmt.limit(count).where(Chart.const == query_level)
                    elif (
                        level.endswith("+") and level[:-1].isnumeric()
                    ) or level.isnumeric():
                        stmt = stmt.limit(count).where(Chart.level == level)
                    else:
                        msg = "Please enter a valid level or chart constant."
                        raise commands.BadArgument(msg)
                except ValueError:
                    msg = "Please enter a valid level or chart constant."
                    raise commands.BadArgument(msg) from None

                charts = (await session.execute(stmt)).scalars().all()

            if len(charts) == 0:
                await ctx.reply("No charts found.", mention_author=False)
                return

            master_song_ids = [
                chart.song.id for chart in charts if chart.difficulty == "MAS"
            ]

            if not course_mode:
                if XL_TECHNO_SONG_ID in master_song_ids:
                    await ctx.reply(XL_TECHNO_JUMPSCARE, mention_author=False)
                    return
                if VOLCANIC_SONG_ID in master_song_ids:
                    await ctx.reply(VOLCANIC_JUMPSCARE, mention_author=False)
                    return
                if (
                    CROSSMYTHOS_RHAPSODIA_SONG_ID in master_song_ids
                    and FORSAKEN_TALE_SONG_ID in master_song_ids
                    and (
                        # since there's only 4 15.7s in the game as of current,
                        # if we do a random 15.7 then the jumpscare will always show up
                        # without this guard.
                        level != "15.7" or random.random() < 0.25
                    )
                ):
                    await ctx.reply(
                        random.choice(
                            [CROSSMYTHOS_RHAPSODIA_JUMPSCARE, FORSAKEN_TALE_JUMPSCARE]
                        ),
                        mention_author=False,
                    )
                    return
                if CROSSMYTHOS_RHAPSODIA_SONG_ID in master_song_ids and (
                    # since there's only 4 15.7s in the game as of current,
                    # if we do a random 15.7 then the jumpscare will always show up
                    # without this guard.
                    level != "15.7" or random.random() < 0.25
                ):
                    await ctx.reply(
                        CROSSMYTHOS_RHAPSODIA_JUMPSCARE, mention_author=False
                    )
                    return
                if FORSAKEN_TALE_SONG_ID in master_song_ids and (
                    # since there's only 4 15.7s in the game as of current,
                    # if we do a random 15.7 then the jumpscare will always show up
                    # without this guard.
                    level != "15.7" or random.random() < 0.25
                ):
                    await ctx.reply(FORSAKEN_TALE_JUMPSCARE, mention_author=False)
                    return
                if TOA_CHAN_TOYBOX_SONG_ID in master_song_ids:
                    await ctx.reply(TOA_CHAN_TOYBOX_JUMPSCARE, mention_author=False)
                    return
                if SOUTHERN_CROSS_SONG_ID in master_song_ids:
                    await ctx.reply(SOUTHERN_CROSS_JUMPSCARE, mention_author=False)
                    return

            embeds: list[discord.Embed] = [
                ChartCardEmbed(
                    chart, synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket
                )
                for chart in charts
            ]
            await ctx.reply(content=content, embeds=embeds, mention_author=False)

    @commands.hybrid_command("recommend")
    @logged_prefix_command
    async def recommend(
        self,
        ctx: PenguinContext,
        count: Range[int, 1, 10] = 3,
        target_rating: Optional[float] = None,
    ):
        """Get random chart recommendations with target scores based on your rating.

        Please note that recommended charts are generated randomly and are independent of your high scores.

        Parameters
        ----------
        count: int
            Number of charts to return. Must be between 1 and 4.
        target_rating: Optional[float]
            Your target play rating. If not provided, it will be automatically set based on your song records
            on CHUNITHM-NET or your Kamaitachi NaiveRating, assuming you're logged in.
        """

        async with ctx.typing(), self.bot.begin_db_session() as session:
            if target_rating is None:
                network = await self.utils.choose_preferred_network(ctx)

                if network == "kamaitachi":
                    async with self.utils.kamaitachi_client(ctx) as client:
                        resp = await client.get(
                            "https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single"
                        )
                        data = json_loads(resp.content)

                        if not data["success"]:
                            msg = f"Could not get Kamaitachi game stats: {data['description']}"
                            raise commands.CommandError(msg)

                        stats = data["body"]
                        target_rating = stats["gameStats"]["ratings"]["naiveRating"]
                else:
                    async with self.utils.chuninet(ctx) as client:
                        records = await self.utils.hydrate_records(
                            await client.best30()
                        )
                        # TODO: should ideally have separate recommendations for b30 and n20?
                        # new_records = await self.utils.hydrate_records(
                        #     await client.new20()
                        # )

                        # get the song with the lowest rating in b30
                        min_rating = min(
                            (item.extras[KEY_PLAY_RATING] for item in records),
                            default=Decimal(0),
                        )
                        # set target rating to be 0.05 above the song with lowest rating in b30
                        target_rating = float(min_rating) + 0.05

            # set minimum target rating to 1 to prevent funny things from happening
            if target_rating is None or target_rating < 1:
                target_rating = 1

            # Determine min-max const to recommend based on target rating.
            min_level = round(target_rating - 2.15, 2)

            if target_rating < 12:
                max_level = round(target_rating - 1, 2)
            else:
                max_level = round(target_rating - 1.5, 2)

            stmt = (
                select(Chart)
                .join(Song, Chart.song_id == Song.id)
                .where(
                    (Chart.const >= min_level)
                    & (Chart.const <= max_level)
                    & (Song.available.is_(True))
                )
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

                target_score = calculate_score_for_rating(target_rating, chart.const)
                if target_score is None:
                    target_score = 1_009_000
                target_score = round_to_nearest(target_score, 50)

                embeds.append(
                    ChartCardEmbed(
                        chart,
                        target_score=target_score,
                        synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
                    )
                )
            await ctx.reply(embeds=embeds, mention_author=False)

    @commands.hybrid_command("whatif")
    @logged_prefix_command
    async def whatif(
        self,
        ctx: Context,
        play_rating: Range[float, 0.0, round(MAX_DIFFICULTY + 2.15, 2)],
        current_play_rating: Optional[
            Range[float, 0.0, round(MAX_DIFFICULTY + 2.15, 2)]
        ] = None,
    ):
        """What if you get a new play with a certain play rating?

        Parameters
        ----------
        play_rating: float
            The play rating you would achieve.
        current_play_rating: Optional[float]
            The current play rating of the chart if it is already in your best 50 scores.
            Leave blank if the chart is currently not included in your best 50 scores.
        """

        async with ctx.typing():
            play_rating = round(play_rating, 2)
            if current_play_rating is not None:
                current_play_rating = round(current_play_rating, 2)
                if play_rating < current_play_rating:
                    # swap the input parameters because we're nice
                    play_rating, current_play_rating = current_play_rating, play_rating
                elif play_rating == current_play_rating:
                    await ctx.reply(
                        "That wouldn't give you any rating increase! What are you expecting?",
                        mention_author=False,
                    )
                    return

            network = await self.utils.choose_preferred_network(ctx)

            if network == "kamaitachi":
                async with self.utils.kamaitachi_client(ctx) as client:
                    resp = await client.get(
                        "https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single/pbs/best?alg=rating"
                    )
                    data = json_loads(resp.content)
                    pbs = convert_kt_pbs_to_records(data["body"])
                    pbs = await self.utils.hydrate_records(pbs)
                    records = pbs[:50]
                    records = await self.utils.hydrate_records(records)
                    record_count = len(records)

                    # get the song with lowest rating in b50
                    min_rating = min(
                        (item.extras[KEY_PLAY_RATING] for item in records),
                        default=Decimal(0),
                    )

                    # calculate raw NaiveRating
                    total_rating = sum(
                        (item.extras[KEY_PLAY_RATING] for item in records),
                        start=Decimal(0),
                    )
                    overall_average = floor_to_ndp(total_rating / 50, 4)

                    if current_play_rating is not None:
                        rating_increase = Decimal(
                            (play_rating - current_play_rating) / 50
                        )
                        updated_rating = overall_average + rating_increase
                        res = f"Replacing a **{current_play_rating:.2f}** rating play with a **{play_rating:.2f}** rating play in your best 50 would give:"
                        res += f"\n- NaiveRating: **+{rating_increase:.4f}** ({overall_average:.4f} → {updated_rating:.4f})"
                    else:
                        res = f"Getting a **{play_rating:.2f}** rating play for a chart currently not in your best 50 would give:"

                        rating_increase = max(
                            (Decimal(play_rating) - min_rating) / 50, 0
                        )
                        if record_count < 50:
                            rating_increase = Decimal(play_rating) / 50
                        updated_rating = overall_average + rating_increase
                        res += f"\n- NaiveRating: **+{rating_increase:.4f}** ({overall_average:.4f} → {updated_rating:.4f})"
                        if record_count == 50 and rating_increase > 0:
                            res += f", replacing a {min_rating:.2f} rating play"

                    await ctx.reply(res, mention_author=False)
                    return

            async with self.utils.chuninet(ctx) as client:
                records = await self.utils.hydrate_records(await client.best30())
                new_records = await self.utils.hydrate_records(await client.new20())

                # check the number of songs in b30
                record_count = len(records)
                # check the number of songs in n20
                new_record_count = len(new_records)

                # get the song with lowest rating in b30
                min_rating = min(
                    (item.extras[KEY_PLAY_RATING] for item in records),
                    default=Decimal(0),
                )
                # get the song with lowest rating in n20
                new_min_rating = min(
                    (item.extras[KEY_PLAY_RATING] for item in new_records),
                    default=Decimal(0),
                )

                # calculate raw rating
                total_rating = sum(
                    (item.extras[KEY_PLAY_RATING] for item in records), start=Decimal(0)
                )
                new_total_rating = sum(
                    (item.extras[KEY_PLAY_RATING] for item in new_records),
                    start=Decimal(0),
                )
                overall_average = floor_to_ndp(
                    (total_rating + new_total_rating) / 50, 4
                )

                if current_play_rating is not None:
                    rating_increase = Decimal((play_rating - current_play_rating) / 50)
                    updated_rating = overall_average + rating_increase
                    res = f"Replacing a **{current_play_rating:.2f}** rating play with a **{play_rating:.2f}** rating play in your best 50 would give:"
                    res += f"\n- Rating: **+{rating_increase:.4f}** ({overall_average:.4f} → {updated_rating:.4f})"
                else:
                    res = f"Getting a **{play_rating:.2f}** rating play for a chart currently not in your best 50 would give:"

                    # calculation in case of old chart
                    rating_increase = max((Decimal(play_rating) - min_rating) / 50, 0)
                    if record_count < 30:
                        rating_increase = Decimal(play_rating) / 50
                    updated_rating = overall_average + rating_increase
                    res += f"\n- Rating: **+{rating_increase:.4f}** ({overall_average:.4f} → {updated_rating:.4f}) if this is an old chart"
                    if record_count == 30 and rating_increase > 0:
                        res += f", replacing a {min_rating:.2f} rating play"

                    # calculation in case of new chart
                    rating_increase = max(
                        (Decimal(play_rating) - new_min_rating) / 50, 0
                    )
                    if new_record_count < 20:
                        rating_increase = Decimal(play_rating) / 50
                    updated_rating = overall_average + rating_increase
                    res += f"\n- Rating: **+{rating_increase:.4f}** ({overall_average:.4f} → {updated_rating:.4f}) if this is a new chart"
                    if new_record_count == 20 and rating_increase > 0:
                        res += f", replacing a {new_min_rating:.2f} rating play"

                await ctx.reply(res, mention_author=False)

    async def song_title_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.autocompleters.song_title_autocomplete(interaction, current)

    @commands.hybrid_command("border")
    @app_commands.autocomplete(query=song_title_autocomplete)
    @logged_prefix_command
    async def border(
        self,
        ctx: PenguinContext,
        difficulty_or_notecount: str,
        *,
        query: Annotated[str | None, AliasNameConverter(lower=True)] = None,
    ):
        """Display the number of permissible JUSTICE, ATTACK and MISS to achieve specific ranks on a chart.

        The values are based on realistic JUSTICE:ATTACK:MISS ratios and are for reference only.
        In terms of scoring, the score decrease from 1 ATTACK is equivalent to 51 JUSTICE, and 1 MISS is equivalent to 101 JUSTICE.

        Parameters
        ----------
        difficulty_or_notecount: str | int
            Chart difficulty to search for (BAS/ADV/EXP/MAS/ULT/WE). Alternatively, enter a notecount here to get the border for that specific notecount.
        query: str
            Song title to search for. You don't have to be exact; try things out!
        """

        async with ctx.typing():
            if difficulty_or_notecount.isnumeric():
                notecount = int(difficulty_or_notecount)

                if notecount <= 0:
                    msg = "Notecount should be larger than 0."
                    raise commands.BadArgument(msg)

                if (
                    notecount
                    > 99_999_999_999_999_999_999_999_999_999_999_999_999_999_999_999
                ):
                    msg = "Notecount is too large."
                    raise commands.BadArgument(msg)

                deductions = calculate_score_deduction_per_judgement(notecount)

                embed = discord.Embed(
                    color=discord.Color.yellow(),
                    title="Rank borders and deductions",
                )
                embed.add_field(name="Note Count", value=str(notecount), inline=False)

                borders = calculate_border(notecount)
                borders_field_value = ""

                for rank, judgements in borders.items():
                    borders_field_value += f"▸ {rank_icon(rank)} ▸ {judgements.justice}-{judgements.attack}-{judgements.miss}\n"

                embed.add_field(
                    name="Borders (JUSTICE-ATTACK-MISS)",
                    value=borders_field_value.strip(),
                )

                deductions = calculate_score_deduction_per_judgement(notecount)
                embed.add_field(
                    name="Score Deduction",
                    value=(
                        f"▸ JUSTICE: -{deductions['justice']:.2f}\n"
                        f"▸ ATTACK: -{deductions['attack']:.2f}\n"
                        f"▸ MISS: -{deductions['miss']:.2f}\n"
                    ),
                )

                await ctx.respond_or_edit(embed=embed)
            else:
                if query is None:
                    raise commands.MissingRequiredArgument(ctx.command.params["query"])  # pyright: ignore[reportOptionalMemberAccess]

                difficulty = await DifficultyConverter().convert(
                    ctx, difficulty_or_notecount
                )
                chart = await ctx.find_chart(
                    difficulty,
                    query,
                    "Select a chart to view rank borders for:",
                )

                if chart.maxcombo is None:
                    song = chart.song
                    msg = f"We currently don't have note counts for {escape_markdown(song.title)} [{chart.difficulty}]. Try using `{ctx.clean_prefix}border <notecount>` instead."

                    raise commands.CommandError(msg)

                await ctx.respond_or_edit(
                    embed=ChartCardEmbed(
                        chart,
                        border=True,
                        synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
                    )
                )

    @commands.hybrid_command("chart")
    @commands.bot_has_permissions(attach_files=True)
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name="BASIC", value="BASIC"),
            app_commands.Choice(name="ADVANCED", value="ADVANCED"),
            app_commands.Choice(name="EXPERT", value="EXPERT"),
            app_commands.Choice(name="MASTER", value="MASTER"),
            app_commands.Choice(name="ULTIMA", value="ULTIMA"),
            app_commands.Choice(name="WORLD'S END", value="WORLD'S END"),
        ]
    )
    @app_commands.autocomplete(query=song_title_autocomplete)
    @logged_prefix_command
    async def chart(
        self,
        ctx: PenguinContext,
        difficulty: Annotated[Difficulty, DifficultyConverter],
        *,
        query: Annotated[str, AliasNameConverter(lower=True)],
    ):
        """Renders a chart view from sdvx.in for a given song and difficulty.

        Parameters
        ----------
        difficulty: str
            Chart difficulty to search for.
        query: str
            Song title to search for. You don't have to be exact; try things out!
        """

        async with ctx.typing():
            chart = await ctx.find_chart(
                difficulty, query, "Select a chart to see chart view for:"
            )
            song = chart.song

            chart_display_name = f"{escape_markdown(song.title)} [{difficulty} {chart.const or chart.level}]"

            if chart.sdvxin_chart_view is None:
                msg = f"Chart view is not available for {chart_display_name} yet. Please try again later."
                raise commands.CommandError(msg)

            sdvxin_id = chart.sdvxin_chart_view.id

            if chart.difficulty == "WE":
                end_index = chart.sdvxin_chart_view.end_index

                bg_url = f"https://sdvx.in/chunithm/end/bg/{sdvxin_id}bg.png"
                data_url = f"https://sdvx.in/chunithm/end/obj/data{sdvxin_id}end{end_index}.png"
                bar_url = f"https://sdvx.in/chunithm/end/bg/{sdvxin_id}bar.png"
            elif chart.difficulty == "ULT":
                bg_url = f"https://sdvx.in/chunithm/ult/bg/{sdvxin_id}bg.png"
                data_url = f"https://sdvx.in/chunithm/ult/obj/data{sdvxin_id}ult.png"
                bar_url = f"https://sdvx.in/chunithm/ult/bg/{sdvxin_id}bar.png"
            else:
                sdvxin_difficulty = (
                    chart.difficulty.lower() if chart.difficulty != "MAS" else "mst"
                )
                bg_url = (
                    f"https://sdvx.in/chunithm/{sdvxin_id[:2]}/bg/{sdvxin_id}bg.png"
                )
                data_url = f"https://sdvx.in/chunithm/{sdvxin_id[:2]}/obj/data{sdvxin_id}{sdvxin_difficulty}.png"
                bar_url = (
                    f"https://sdvx.in/chunithm/{sdvxin_id[:2]}/bg/{sdvxin_id}bar.png"
                )

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout=60.0),
                follow_redirects=True,
                transport=httpx.AsyncHTTPTransport(retries=5),
            ) as client:
                bg_resp, data_resp, bar_resp = await asyncio.gather(
                    client.get(bg_url),
                    client.get(data_url),
                    client.get(bar_url),
                )

            if bg_resp.is_error or data_resp.is_error or bar_resp.is_error:
                msg = f"Failed to fetch chart view for {chart_display_name}. Please try again later."
                raise commands.CommandError(msg)

            output = await asyncio.to_thread(
                compose_chart_view, bg_resp.content, data_resp.content, bar_resp.content
            )

            if song.bpm is not None:
                displayed_bpm = str(song.bpm)

                if (
                    song.min_bpm is not None
                    and song.max_bpm is not None
                    and song.min_bpm != song.max_bpm
                ):
                    displayed_bpm = f"{displayed_bpm} ({song.min_bpm}~{song.max_bpm})"
            else:
                displayed_bpm = "Unknown"

            content = (
                f"**{chart_display_name}**\n"
                f"BPM: {displayed_bpm}\n"
                f"CHAIN: {chart.maxcombo or '-'} / TAP: {chart.tap or '-'} / HOLD: {chart.hold or '-'} / SLIDE: {chart.slide or '-'} / AIR: {chart.air or '-'} / FLICK: {chart.flick or '-'}\n"
            )

            if chart.charter is not None:
                content += f"NOTES DESIGNER: {escape_markdown(chart.charter)}\n"

            content += f"-# [sdvx.in](<{sdvxin_link(chart.sdvxin_chart_view)}>) • [Search on YouTube](<{yt_search_link(song.title, chart.difficulty, chart.level)}>)"

            file = discord.File(
                output,
                filename=f"{sdvxin_id}{chart.difficulty.lower()}.jpg",
                description=f"Chart view for {chart_display_name}",
            )

            await ctx.respond_or_edit(content, files=[file])

    @commands.hybrid_command("odex")
    @logged_prefix_command
    async def odex(self, ctx: Context):
        """Read the Codex."""

        await ctx.reply(
            content="[Read the Codex.](https://chunithm.org)",
            mention_author=False,
        )


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

TOA_CHAN_TOYBOX_SONG_ID = 2428
TOA_CHAN_TOYBOX_JUMPSCARE = """恐怖！とあちゃんのおもちゃ箱！
😂🟦🟦
      🟦     🟦
      🟦     ⚡
      🟦          ⚡
😂🟦               😂
      🟦             ➡️
      🟦       ➡️
      🟦➡️
      🟦       ⬅️
      🟦             ⬅️
      🟦       ➡️
      🟦➡️
      🟦       ⬅️
      🟦             ⬅️
      🟦       ➡️
      🟦➡️
      🟦       ⬅️
      🟦             ⬅️
      🟦     😡
      🟦           😡
      🟦     😡
      🟦           😡
      🟦    😡
      🟦          😡"""  # noqa: RUF001, W291

CROSSMYTHOS_RHAPSODIA_SONG_ID = 2802
CROSSMYTHOS_RHAPSODIA_JUMPSCARE = """恐怖！Crossmythos Rhapsodia！

😠　　　😠
　😡　😡
　　😡
　😠　😠
😡　😡
　😡
😠　😠
　😡　😡
　　😡
　😠　😠
　　😡　😡
　　　😡
　　😠　😠"""  # noqa: RUF001

SOUTHERN_CROSS_SONG_ID = 2780
SOUTHERN_CROSS_JUMPSCARE = """恐怖！Southern Cross！
　 😡
😡
　 😡
😡　 😠 ↗️
　 😡
😡
　 😡
😡　 😠 ↗️
　 😡
😡
　 😡
😡　 😠 ↗️"""  # noqa: RUF001


async def setup(bot: "ChuniBot"):
    await bot.add_cog(ToolsCog(bot))
