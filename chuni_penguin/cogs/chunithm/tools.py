# ruff: noqa: RUF003
import asyncio
import decimal
import itertools
import random
from contextlib import closing
from decimal import Decimal
from io import BytesIO
from math import ceil
from typing import TYPE_CHECKING, Annotated, Literal, Optional, Sequence

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context, Range
from discord.utils import escape_markdown
from PIL import Image
from sqlalchemy import Row, func, select, text
from sqlalchemy.orm import joinedload

from chuni_penguin import flags
from chuni_penguin.calculation import (
    calculate_border,
    calculate_overpower_base,
    calculate_overpower_max,
    calculate_play_overpower,
    calculate_rating,
    calculate_score_deduction_per_judgement,
    calculate_score_for_rating,
)
from chuni_penguin.config import config
from chuni_penguin.constants import MAX_DIFFICULTY
from chuni_penguin.context import PenguinContext
from chuni_penguin.converters import (
    AliasNameConverter,
    AliasNameTransformer,
    DecimalConverter,
    DecimalTransformer,
    DifficultyConverter,
    LevelRange,
    LevelRangeConverter,
)
from chuni_penguin.database import Chart, PersonalBest, Song
from chuni_penguin.logging import logged_app_command, logged_prefix_command
from chuni_penguin.types import (
    ComboLamp,
    Difficulty,
    Rank,
    RatingFrame,
    RatingFrameType,
    RatingType,
)
from chuni_penguin.ui import ChartCardEmbed
from chuni_penguin.utils import (
    floor_to_ndp,
    get_jacket_url,
    round_to_nearest,
    sdvxin_link,
    yt_search_link,
)

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot
    from chuni_penguin.cogs.autocompleters import AutocompletersCog


def compose_chart_view(bg: bytes, data: bytes, bar: bytes):
    with (
        Image.open(BytesIO(bg)) as bg_img,
        Image.open(BytesIO(data)) as data_img,
        Image.open(BytesIO(bar)) as bar_img,
    ):
        if bg_img.mode != "RGBA":
            bg_img_new = bg_img.convert("RGBA")
            bg_img.close()
            bg_img = bg_img_new

        if data_img.mode != "RGBA":
            data_img_new = data_img.convert("RGBA")
            data_img.close()
            data_img = data_img_new

        if bar_img.mode != "RGBA":
            bar_img_new = bar_img.convert("RGBA")
            bar_img.close()
            bar_img = bar_img_new

        with (
            closing(Image.new("RGBA", bg_img.size, (0, 0, 0, 255))) as background,
            closing(bg_img),
        ):
            result = Image.alpha_composite(background, bg_img)

        if data_img.size != bg_img.size:
            container = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
            container.paste(data_img, (0, 0), data_img)
            data_img.close()
            data_img = container

        with closing(result), closing(data_img):
            result = Image.alpha_composite(result, data_img)

        if bar_img.size != bg_img.size:
            container = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
            container.paste(bar_img, (0, 0), bar_img)
            bar_img.close()
            bar_img = container

        with closing(result), closing(bar_img):
            result = Image.alpha_composite(result, bar_img)

        output = BytesIO()

        with closing(result):
            result_rgb = result.convert("RGB")

            result_rgb.save(output, format="JPEG", quality=92)
            result_rgb.close()

    output.seek(0)

    return output


def rating_reach_content(
    rating_type: RatingType,
    target_rating: Decimal,
    current_rating: Decimal,  # should be 4dp for best results
    total_scores: int,
    frame: RatingFrame,
    each: Decimal | None,
    count: int | None,
):
    if each is None and (count is None or count == 1):
        # Reach goal with only one score
        raw_rating_required = (target_rating - current_rating) * total_scores
        frame_floor = (
            (frame.scores[-1].rating or Decimal(0))
            if len(frame.scores) == frame.num_scores
            else Decimal(0)
        )
        play_rating_required = ceil((frame_floor + raw_rating_required) * 100) / 100

        return (
            f"To reach {target_rating:.2f} {rating_type} with one score in your "
            f"{frame.type.name}{frame.num_scores}, you need to set a **{play_rating_required:.2f}** "
            f"rating play."
        ) + (
            " Good luck, I guess."
            if play_rating_required >= calculate_rating(1010000, MAX_DIFFICULTY)
            else ""
        )
    if (
        each is not None
        and len(frame.scores) == frame.num_scores
        and frame.scores[-1].rating is not None
        and each < frame.scores[-1].rating
    ):
        # Given rating is below best50 floor
        return (
            f"New {frame.type.name}{frame.num_scores} scores require "
            f"at least **{frame.scores[-1].rating:.2f}** rating, so {target_rating:.2f} {rating_type} "
            f"can't be reached with {each:.2f} rating scores."
        )
    if each is not None:
        # Given rating would be in best50
        num_scores = 0
        # Rating list from bottom to top, fill in unfilled slots with 0 rating
        ratings = [Decimal(0)] * (frame.num_scores - len(frame.scores)) + [
            frame.scores[-(i + 1)].rating or Decimal(0)
            for i in range(len(frame.scores))
        ]

        for rating in ratings:
            if rating >= each:
                break

            current_rating += (each - rating) / 50
            num_scores += 1

            if current_rating >= target_rating:
                break

        if current_rating >= target_rating:
            return (
                f"To reach {target_rating:.2f} {rating_type}, you need to set **{num_scores}** "
                f"score{'s' if num_scores > 1 else ''} of **{each:.2f}** rating in your "
                f"{frame.type.name}{frame.num_scores}."
            )

        return (
            f"Filling up your {frame.type.name}{frame.num_scores} with {each:.2f} rating "
            f"plays would only lead to {current_rating:.4f} {rating_type}, which is still less "
            f"than {target_rating:.2f} {rating_type}."
        )

    if count is not None:
        if count > frame.num_scores:
            return f"{count} scores is more than the number of scores in {frame.type.name}{frame.num_scores}."

        # count is not None and count > 1 (because first condition checks count == 1)
        # calculate play rating needed for each play to achieve the given rating
        # Ratings of bottom n plays.
        # - If there are more than `count` unfilled slots, take a list of `count` 0s.
        # - If there are less than `count` unfilled slots, take a list of 0s of unfilled
        # slots, and then take the rest from the given data.
        ratings = [Decimal(0)] * min(count, frame.num_scores - len(frame.scores)) + [
            frame.scores[-(i + 1)].rating or Decimal(0)
            for i in range(max(0, count - (frame.num_scores - len(frame.scores))))
        ]

        # Find the minimum rating to replace each entry in `ratings` with so that
        # it reaches the new target rating.
        raw_rating_required = (target_rating - current_rating) * total_scores
        required = (
            Decimal(
                ceil(
                    (sum(ratings, Decimal(0)) + raw_rating_required)
                    / len(ratings)
                    * 100
                )
            )
            / 100
        )
        count_less_than_required = sum(
            1
            for entry in frame.scores
            if entry.rating is None or entry.rating < required
        )

        return (
            (
                f"To reach {target_rating:.2f} {rating_type} with {count} score{'s' if count > 1 else ''} "
                f"of the same rating in {frame.type.name}{frame.num_scores}, each of them "
                f"would need to be **{required:.2f}** rating"
            )
            + (
                f", but you only have {count_less_than_required} scores less than {required:.2f} rating."
                if count_less_than_required < count
                else "."
            )
            + (
                " Good luck, I guess."
                if required >= calculate_rating(1010000, MAX_DIFFICULTY)
                else ""
            )
        )

    return "Uh oh, you hit a bug! Please annoy beerpsi."


def whatif_content(
    frame: RatingFrame,
    current_rating: Decimal,
    play_rating: Decimal,
    text_before_replacing: str = "",
):
    replacing: Decimal | None = None

    if len(frame.scores) < frame.num_scores:
        rating_increase = floor_to_ndp(play_rating / 50, 4)
    else:
        replacing = frame.scores[-1].rating or Decimal(0)
        rating_increase = max((Decimal(play_rating) - replacing) / 50, Decimal(0))

    return (
        f"**+{rating_increase:.4f}** ({current_rating:.4f} → {current_rating + rating_increase:.4f}){text_before_replacing}"
        + (
            f", replacing a {replacing:.2f} rating play"
            if replacing is not None and rating_increase > 0
            else ""
        )
    )


class ToolsCog(commands.Cog, name="Tools"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils = self.bot.utils
        self.autocompleters: "AutocompletersCog" = self.bot.get_cog("Autocompleters")  # type: ignore[reportGeneralTypeIssues]
        self.http_client = self.bot.caching_http_client
        self._rng = random.Random()

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
                    overpower_ap = calculate_play_overpower(
                        overpower_base, ComboLamp.all_justice
                    )
                    overpower_ap_percentage = floor_to_ndp(
                        overpower_ap / overpower_max * 100, 2
                    )
                    res += f"\n  - AJ: **{overpower_ap} / {overpower_max_floored} ({overpower_ap_percentage}%)**"

                overpower_fc = calculate_play_overpower(
                    overpower_base, ComboLamp.full_combo
                )
                overpower_fc_percentage = floor_to_ndp(
                    overpower_fc / overpower_max * 100, 2
                )
                overpower_base_percentage = floor_to_ndp(
                    overpower_base / overpower_max * 100, 2
                )

                res += f"\n  - FC: **{overpower_fc} / {overpower_max_floored} ({overpower_fc_percentage}%)**"
                res += f"\n  - Non-FC: **{overpower_base} / {overpower_max_floored} ({overpower_base_percentage}%)**"

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
            if score >= Rank.ss.min_score:
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
                        score == Rank.sss.min_score
                        or score == Rank.ssp.min_score
                        or score == Rank.ss.min_score
                        or score == Rank.sp.min_score
                        or score == Rank.s.min_score
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

            if required_score is not None and required_score >= Rank.s.min_score:
                res += f"\n {chart_constant_10 / 10:>4.1f} | {int(required_score):>7}"
            if chart_constant_10 >= 100:
                chart_constant_10 += 1
            elif chart_constant_10 >= 70:
                chart_constant_10 += 5
            else:
                chart_constant_10 += 10
        res += "```"

        await ctx.reply(res, mention_author=False)

    @commands.hybrid_command("random", aliases=["rand"])
    @logged_prefix_command
    async def random(
        self, ctx: PenguinContext, level: str, count: Range[int, 1, 10] = 3
    ):
        """Get random charts based on level/course/chart constant.

        Parameters
        ----------
        level: str
            Level to search for. Can be a level (13+), a chart constant (13.5), a level
            range (14.0-14.8), or a course class (`i`, `ii`, `iii`, `iv`, `v`, `inf`,
            `random`, `wallpanic`).
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

        async with ctx.typing(), self.bot.begin_db_read() as session:
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
                stmt = stmt.limit(count)
                levels = await LevelRangeConverter().convert(ctx, level)

                if isinstance(levels, LevelRange):
                    min_level, max_level = levels

                    if min_level is not None:
                        stmt = stmt.where(
                            Chart.const >= (min_level.const or min_level.inferred_const)
                        )

                    if max_level is not None:
                        stmt = stmt.where(
                            Chart.const
                            <= (max_level.const or max_level.inferred_max_const)
                        )
                elif levels.const is not None:
                    stmt = stmt.where(Chart.const == levels.const)
                else:
                    stmt = stmt.where(Chart.level == levels.level)

                charts = (await session.execute(stmt)).scalars().all()

            if len(charts) == 0:
                await ctx.reply("No charts found.", mention_author=False)
                return

            master_song_ids = [
                chart.song.id for chart in charts if chart.difficulty == "MAS"
            ]

            if not course_mode:
                if XL_TECHNO_SONG_ID in master_song_ids:
                    await ctx.bot.database.user_found_easter_egg(
                        ctx.author.id, "xl-techno-more-dance-remix-jumpscare"
                    )
                    await ctx.reply(XL_TECHNO_JUMPSCARE, mention_author=False)
                    return
                if VOLCANIC_SONG_ID in master_song_ids:
                    await ctx.bot.database.user_found_easter_egg(
                        ctx.author.id, "volcanic-jumpscare"
                    )
                    await ctx.reply(VOLCANIC_JUMPSCARE, mention_author=False)
                    return
                if (
                    CROSSMYTHOS_RHAPSODIA_SONG_ID in master_song_ids
                    and FORSAKEN_TALE_SONG_ID in master_song_ids
                    and (
                        # since there's only 4 15.7s in the game as of current,
                        # if we do a random 15.7 then the jumpscare will always show up
                        # without this guard.
                        level != "15.7" or self._rng.random() < 0.25
                    )
                ):
                    if self._rng.random() > 0.5:
                        await ctx.bot.database.user_found_easter_egg(
                            ctx.author.id, "crossmythos-rhapsodia-jumpscare"
                        )
                        jumpscare = CROSSMYTHOS_RHAPSODIA_JUMPSCARE
                    else:
                        await ctx.bot.database.user_found_easter_egg(
                            ctx.author.id, "forsaken-tale-jumpscare"
                        )
                        jumpscare = FORSAKEN_TALE_JUMPSCARE

                    await ctx.reply(jumpscare, mention_author=False)
                    return
                if CROSSMYTHOS_RHAPSODIA_SONG_ID in master_song_ids and (
                    # since there's only 4 15.7s in the game as of current,
                    # if we do a random 15.7 then the jumpscare will always show up
                    # without this guard.
                    level != "15.7" or self._rng.random() < 0.25
                ):
                    await ctx.bot.database.user_found_easter_egg(
                        ctx.author.id, "crossmythos-rhapsodia-jumpscare"
                    )
                    await ctx.reply(
                        CROSSMYTHOS_RHAPSODIA_JUMPSCARE, mention_author=False
                    )
                    return
                if FORSAKEN_TALE_SONG_ID in master_song_ids and (
                    # since there's only 4 15.7s in the game as of current,
                    # if we do a random 15.7 then the jumpscare will always show up
                    # without this guard.
                    level != "15.7" or self._rng.random() < 0.25
                ):
                    await ctx.bot.database.user_found_easter_egg(
                        ctx.author.id, "forsaken-tale-jumpscare"
                    )
                    await ctx.reply(FORSAKEN_TALE_JUMPSCARE, mention_author=False)
                    return
                if TOA_CHAN_TOYBOX_SONG_ID in master_song_ids:
                    await ctx.bot.database.user_found_easter_egg(
                        ctx.author.id, "toa-chans-toybox-jumpscare"
                    )
                    await ctx.reply(TOA_CHAN_TOYBOX_JUMPSCARE, mention_author=False)
                    return
                if SOUTHERN_CROSS_SONG_ID in master_song_ids:
                    await ctx.bot.database.user_found_easter_egg(
                        ctx.author.id, "southern-cross-jumpscare"
                    )
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

        Please note that recommended charts are generated randomly.

        Parameters
        ----------
        count: int
            Number of charts to return. Must be between 1 and 4.
        target_rating: Optional[float]
            Your target play rating. If not provided, it will be automatically set based on your song records
            on CHUNITHM-NET or your Kamaitachi NaiveRating, assuming you're logged in.
        """

        async with ctx.typing():
            if target_rating is None:
                async with (
                    self.bot.begin_db_read() as session,
                    ctx.bot.chunithm_networks.network(ctx) as client,
                ):
                    naive_best50 = (
                        select(PersonalBest.rating)
                        .where(
                            (PersonalBest.discord_id == ctx.author.id)
                            & (PersonalBest.network == client.NAME)
                            & (PersonalBest.rating.is_not(None))
                        )
                        .order_by(PersonalBest.rating.desc())
                        .limit(50)
                    ).subquery()

                    target_rating = (
                        await session.execute(func.avg(naive_best50.c.rating))
                    ).scalar_one_or_none()

                    target_rating = (
                        int(target_rating) / 100 if target_rating is not None else None
                    )

            if target_rating is None:
                msg = "There isn't enough data to give you recommendations. Please try using other score features, or specify a target rating."
                raise commands.CommandError(msg)

            # set minimum target rating to 1 to prevent funny things from happening
            if target_rating is None or target_rating < 1:
                target_rating = 1

            # Determine min-max const to recommend based on target rating.
            min_level = round(target_rating - 2.15, 2)

            if target_rating < 12:
                max_level = round(target_rating - 1, 2)
            else:
                max_level = round(target_rating - 1.5, 2)

            async with self.bot.begin_db_read() as session:
                pb_cte = (
                    select(
                        PersonalBest.song_id,
                        PersonalBest.difficulty,
                        func.max(PersonalBest.score).label("score"),
                    )
                    .where(PersonalBest.discord_id == ctx.author.id)
                    .group_by(PersonalBest.song_id, PersonalBest.difficulty)
                    .cte("personal_bests_all_networks")
                )

                stmt = (
                    select(Chart, pb_cte.c.score)
                    .join(Song, Chart.song_id == Song.id)
                    .join(
                        pb_cte,
                        (pb_cte.c.song_id == Chart.song_id)
                        & (pb_cte.c.difficulty == Chart.difficulty),
                        isouter=True,
                    )
                    .where(
                        (Chart.const >= min_level)
                        & (Chart.const <= max_level)
                        & (Song.available.is_(True))
                    )
                    .order_by(text("RANDOM()"))
                    .options(
                        joinedload(Chart.song), joinedload(Chart.sdvxin_chart_view)
                    )
                )

                charts: Sequence[Row[tuple[Chart, int]]] = (
                    await session.execute(stmt)
                ).all()

            if len(charts) == 0:
                await ctx.reply("No charts found.", mention_author=False)
                return

            embeds: list[discord.Embed] = []
            for row in charts:
                chart, pb = row._tuple()

                assert chart.const is not None

                target_score = calculate_score_for_rating(target_rating, chart.const)

                if target_score is None:
                    target_score = 1_009_000

                target_score = round_to_nearest(target_score, 50)

                if pb is not None and target_score <= pb:
                    continue

                embeds.append(
                    ChartCardEmbed(
                        chart,
                        target_score=target_score,
                        synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
                    )
                )

                if len(embeds) >= count:
                    break

            if len(embeds) <= 0:
                await ctx.reply("No charts found.", mention_author=False)
                return

            await ctx.reply(embeds=embeds, mention_author=False)

    @flags.command("whatif")
    @flags.argument("play_rating", type=Decimal)
    @flags.argument("current_play_rating", nargs="?", default=None, type=Decimal)
    @flags.argument(
        "-r",
        "--rating-system",
        choices=["naive", "ingame"],
        default=None,
        required=False,
    )
    @flags.argument("-k", "--kamaitachi", dest="kamaitachi", action="store_true")
    @logged_prefix_command
    async def whatif(
        self,
        ctx: PenguinContext,
        *,
        play_rating: Decimal,
        current_play_rating: Decimal | None = None,
        rating_system: Literal["naive", "ingame"] | None = None,
        kamaitachi: bool = False,
    ):
        """What if you get a new play with a certain play rating?

        *Parameters*
        `play_rating`: The play rating you would achieve.
        `current_play_rating`: The current play rating of the chart if it is already in your best 50 scores. Leave blank if the chart is currently not included in your best 50 scores.
        `-r`, `--rating-system`: Choose between `ingame` (best30 + new20) or `naive` (best50) (default: depends on network).
        `-k`, `--kamaitachi`: Use your Kamaitachi account instead of your CHUNITHM International account, if both are linked.
        """

        if rating_system == "naive":
            rating_type = RatingType.naive
        elif rating_system == "ingame":
            rating_type = RatingType.in_game
        else:
            rating_type = None

        await self._whatif_impl(
            ctx, play_rating, current_play_rating, rating_type, kamaitachi=kamaitachi
        )

    @app_commands.command(
        name="whatif",
        description="What if you get a new play with a certain play rating?",
    )
    @app_commands.rename(
        play_rating="play-rating", current_play_rating="current-play-rating"
    )
    @app_commands.describe(
        play_rating="The play rating you would achieve.",
        current_play_rating="The current play rating of the chart if it is already in your best 50 scores.",
        rating_system="The rating system to calculate the rating gain for.",
        kamaitachi="Use your Kamaitachi account.",
    )
    @app_commands.choices(
        rating_system=[
            app_commands.Choice(
                name="In-game (Best 30 + New 20)", value=RatingType.in_game.value
            ),
            app_commands.Choice(name="Naive (Best 50)", value=RatingType.naive.value),
        ]
    )
    @logged_app_command
    async def whatif_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        play_rating: app_commands.Transform[Decimal, DecimalTransformer],
        current_play_rating: app_commands.Transform[Decimal | None, DecimalTransformer],
        rating_system: RatingType | None = None,
        *,
        kamaitachi: bool = False,
    ):
        await self._whatif_impl(
            await PenguinContext.from_interaction(interaction),
            play_rating,
            current_play_rating,
            rating_system,
            kamaitachi=kamaitachi,
        )

    async def _whatif_impl(
        self,
        ctx: PenguinContext,
        play_rating: Decimal,
        current_play_rating: Decimal | None,
        rating_type: RatingType | None,
        *,
        kamaitachi: bool = False,
    ):
        play_rating = floor_to_ndp(play_rating, 2)

        if current_play_rating is not None:
            current_play_rating = floor_to_ndp(current_play_rating, 2)

            if play_rating < current_play_rating:
                # swap the input parameters because we're nice
                play_rating, current_play_rating = current_play_rating, play_rating
            elif play_rating == current_play_rating:
                await ctx.reply(
                    "That wouldn't give you any rating increase! What are you expecting?",
                    mention_author=False,
                )
                return

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(ctx, kamaitachi=kamaitachi) as client,
        ):
            if rating_type is None:
                rating_type = client.DEFAULT_RATING_SYSTEM

            breakdown = await client.get_rating_breakdown(rating_type)

        if rating_type == RatingType.in_game:
            best30 = breakdown.frames[RatingFrameType.best]
            new20 = breakdown.frames[RatingFrameType.new]
            total_scores = best30.num_scores + new20.num_scores
            raw_rating = floor_to_ndp(
                sum(
                    (
                        entry.rating or Decimal(0)
                        for entry in itertools.chain(best30.scores, new20.scores)
                    ),
                    Decimal(0),
                )
                / total_scores,
                4,
            )
        elif rating_type == RatingType.naive:
            best50 = breakdown.frames[RatingFrameType.best]
            raw_rating = floor_to_ndp(
                sum(
                    (entry.rating or Decimal(0) for entry in best50.scores),
                    Decimal(0),
                )
                / best50.num_scores,
                4,
            )
        else:
            msg = f"Unsupported rating system {client.DEFAULT_RATING_SYSTEM}."
            raise commands.CommandError(msg)

        if current_play_rating is not None:
            rating_increase = (Decimal(play_rating) - Decimal(current_play_rating)) / 50
            await ctx.respond_or_edit(
                content=(
                    f"Replacing a **{current_play_rating:.2f}** rating play with a **{play_rating:.2f}** rating play in your best 50 would give:\n"
                    f"- {rating_type}: **+{rating_increase:.4f}** ({raw_rating:.4f} → {raw_rating + rating_increase:.4f})"
                )
            )
            return

        if rating_type == RatingType.in_game:
            best30 = breakdown.frames[RatingFrameType.best]
            new20 = breakdown.frames[RatingFrameType.new]

            await ctx.respond_or_edit(
                content=(
                    f"Getting a **{play_rating:.2f}** play for a chart currently not in your best50 would give:\n"
                    f"- {rating_type}: {whatif_content(best30, raw_rating, play_rating, ' if this is an old chart')}\n"
                    f"- {rating_type}: {whatif_content(new20, raw_rating, play_rating, ' if this is a new chart')}"
                )
            )

        elif rating_type == RatingType.naive:
            best50 = breakdown.frames[RatingFrameType.best]

            await ctx.respond_or_edit(
                content=(
                    f"Getting a **{play_rating:.2f}** play for a chart currently not in your best50 would give:\n"
                    f"- {rating_type}: {whatif_content(best50, raw_rating, play_rating)}"
                )
            )
        else:
            msg = f"Unreachable branch {current_play_rating=!r} {rating_type=!r}"
            raise commands.CommandError(msg)

    @flags.command("reach")
    @flags.argument("target")
    @flags.argument(
        "-e", "--each", dest="each", type=DecimalConverter, default=None, required=False
    )
    @flags.argument(
        "-c", "--count", dest="count", type=int, default=None, required=False
    )
    @flags.argument(
        "-r",
        "--rating-system",
        choices=["naive", "ingame"],
        default=None,
        required=False,
    )
    @flags.argument("-k", "--kamaitachi", dest="kamaitachi", action="store_true")
    @logged_prefix_command
    async def reach_prefix(
        self,
        ctx: PenguinContext,
        *,
        target: str,
        each: Decimal | None = None,
        count: int | None = None,
        rating_system: Literal["naive", "ingame"] | None = None,
        kamaitachi: bool = False,
    ):
        """Calculate how many scores of what rating is needed to reach the given rating.

        **Parameters**
        `target`: The target rating to achieve, will be floored to 2 decimal points. Alternatively, prefix the value with a `+` to interpret as a delta relative to your current rating.
        `-e`, `--each`: Fill your best30/new20/best50 with scores of this much rating (floored to 2 decimal points) until the target rating is acheived. (default: None)
        `-c`, `--count`: Specify a number of scores to set to reach the target rating (default: 1).
        `-r`, `--rating-system`: Choose between `ingame` (best30 + new20) or `naive` (best50) (default: depends on network).
        `-k`, `--kamaitachi`: Use your Kamaitachi account instead of your CHUNITHM International account, if both are linked.
        """

        if rating_system == "naive":
            rating_type = RatingType.naive
        elif rating_system == "ingame":
            rating_type = RatingType.in_game
        else:
            rating_type = None

        if count is not None and count <= 0:
            msg = "number of charts must be at least 1"
            raise commands.BadArgument(msg)

        await self._reach_impl(
            ctx, target, each, count, rating_type, kamaitachi=kamaitachi
        )

    @app_commands.command(
        name="reach",
        description="Calculate how many scores of what rating is needed to reach the given rating.",
    )
    @app_commands.rename(rating_system="rating-system")
    @app_commands.describe(
        target="Target rating to achieve, or a delta from your current rating (e.g. +0.01).",
        each="Fill your best30/new20/best50 with scores of this much rating until the target rating is acheived.",
        count="Specify a number of scores to set to reach the target rating.",
        rating_system="The rating system to calculate for.",
        kamaitachi="Use your Kamaitachi account.",
    )
    @app_commands.choices(
        rating_system=[
            app_commands.Choice(
                name="In-game (Best 30 + New 20)", value=RatingType.in_game.value
            ),
            app_commands.Choice(name="Naive (Best 50)", value=RatingType.naive.value),
        ]
    )
    @logged_app_command
    async def reach_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        target: str,
        each: app_commands.Transform[Decimal | None, DecimalTransformer] = None,
        count: app_commands.Range[int, 1] | None = None,
        rating_system: RatingType | None = None,
        *,
        kamaitachi: bool = False,
    ):
        await self._reach_impl(
            await PenguinContext.from_interaction(interaction),
            target,
            each,
            count,
            rating_system,
            kamaitachi=kamaitachi,
        )

    async def _reach_impl(
        self,
        ctx: PenguinContext,
        target: str,
        each: Decimal | None,
        count: int | None,
        rating_type: RatingType | None,
        *,
        kamaitachi: bool,
    ):
        if target.startswith("-"):
            msg = "We don't have recent rating anymore, you can't lose rating until the version changes!"
            raise commands.BadArgument(msg)

        if each is not None and count is not None:
            msg = 'You can only specify one of "each" or "count".'
            raise commands.BadArgument(msg)

        try:
            target_value = floor_to_ndp(Decimal(target), 2)
        except decimal.InvalidOperation:
            msg = f'"{escape_markdown(target)}" is not a valid number.'
            raise commands.BadArgument(msg) from None

        if each is not None:
            each = floor_to_ndp(each, 2)

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(ctx, kamaitachi=kamaitachi) as client,
        ):
            if rating_type is None:
                rating_type = client.DEFAULT_RATING_SYSTEM

            rating_breakdown = await client.get_rating_breakdown(rating_type)

        if target.startswith("+"):
            target_rating = rating_breakdown.rating + target_value
        else:
            target_rating = target_value

        if rating_breakdown.rating >= target_rating:
            await ctx.respond_or_edit(
                f"You have {rating_breakdown.rating:.2f} {rating_type} which is already more than {target_rating}."
            )
            return

        if rating_type == RatingType.in_game:
            best30 = rating_breakdown.frames[RatingFrameType.best]
            new20 = rating_breakdown.frames[RatingFrameType.new]
            total_scores = best30.num_scores + new20.num_scores
            raw_rating = floor_to_ndp(
                sum(
                    (
                        entry.rating or Decimal(0)
                        for entry in itertools.chain(best30.scores, new20.scores)
                    ),
                    Decimal(0),
                )
                / total_scores,
                4,
            )
            await ctx.respond_or_edit(
                (
                    f"- Best 30: {rating_reach_content(rating_type, target_rating, raw_rating, total_scores, best30, each, count)}\n"
                    f"- New 20: {rating_reach_content(rating_type, target_rating, raw_rating, total_scores, new20, each, count)}\n"
                )
            )
        elif rating_type == RatingType.naive:
            best50 = rating_breakdown.frames[RatingFrameType.best]
            raw_rating = floor_to_ndp(
                sum((entry.rating or Decimal(0) for entry in best50.scores), Decimal(0))
                / best50.num_scores,
                4,
            )

            await ctx.respond_or_edit(
                rating_reach_content(
                    rating_type,
                    target_rating,
                    raw_rating,
                    best50.num_scores,
                    best50,
                    each,
                    count,
                )
            )
        else:
            msg = f"Unsupported rating system {client.DEFAULT_RATING_SYSTEM}."
            raise commands.CommandError(msg)

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
                    borders_field_value += f"▸ {config.icons.rank_icon(rank)} ▸ {judgements.justice}-{judgements.attack}-{judgements.miss}\n"

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

                if chart is None:
                    return

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

    async def _fetch_sdvxin_with_fallback(self, chart: Chart, url: str, fallback: str):
        resp = await self.http_client.get(url)

        if resp.is_success:
            return resp

        if resp.is_error and chart.difficulty in ("ULT", "WE"):
            return await self.http_client.get(fallback)

        return resp

    @app_commands.command(
        name="chart",
        description="Renders a chart view from sdvx.in for a given song and difficulty.",
    )
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
    @logged_app_command
    async def chart_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        difficulty: str,
        query: Annotated[str, AliasNameTransformer(lower=True)],
        *,
        mirror: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)
        converted_difficulty = await DifficultyConverter().convert(ctx, difficulty)

        await self._chart_impl(
            ctx, difficulty=converted_difficulty, query=query, mirror=mirror
        )

    @flags.command("chart")
    @flags.argument("-m", "--mirror", action="store_true")
    @flags.argument("difficulty", type=DifficultyConverter)
    @flags.argument("query", nargs="+")
    @logged_prefix_command
    async def chart(
        self,
        ctx: PenguinContext,
        *,
        difficulty: Difficulty,
        query: list[str],
        mirror: bool = False,
    ):
        q = await AliasNameConverter(lower=True).convert(ctx, " ".join(query))

        await self._chart_impl(ctx, difficulty=difficulty, query=q, mirror=mirror)

    async def _chart_impl(
        self,
        ctx: PenguinContext,
        *,
        difficulty: Difficulty,
        query: str,
        mirror: bool = False,
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

            if chart is None:
                return

            song = chart.song
            chart_display_name = f"{escape_markdown(song.title)} [{difficulty} {chart.const or chart.level}]"
            yt_url = yt_search_link(song.title, chart.difficulty)

            if len(yt_url) > 512:
                yt_url = (
                    f"{config.web.base_url}/youtube/{song.id}/{chart.difficulty}"
                    if config.web.is_accessible
                    else None
                )

            if chart.sdvxin_chart_view is None:
                embed = discord.Embed(
                    color=discord.Color.red(),
                    title="Error",
                    description=f"Chart view is not available for {chart_display_name} yet. Please try again later.",
                )

                if yt_url is not None:
                    view = discord.ui.View(timeout=None)
                    view.add_item(
                        discord.ui.Button(
                            style=discord.ButtonStyle.link,
                            label="Search on YouTube",
                            url=yt_url,
                        )
                    )
                else:
                    view = None

                await ctx.respond_or_edit(embed=embed, view=view)
                return

            sdvxin_id = chart.sdvxin_chart_view.id
            data_key = "mirror" if mirror else "data"

            if chart.difficulty == "WE":
                end_index = chart.sdvxin_chart_view.end_index

                bg_url = f"https://sdvx.in/chunithm/end/bg/{sdvxin_id}bg.png"
                data_url = f"https://sdvx.in/chunithm/end/obj/{data_key}{sdvxin_id}end{end_index}.png"
                bar_url = f"https://sdvx.in/chunithm/end/bg/{sdvxin_id}bar.png"
            elif chart.difficulty == "ULT":
                bg_url = f"https://sdvx.in/chunithm/ult/bg/{sdvxin_id}bg.png"
                data_url = (
                    f"https://sdvx.in/chunithm/ult/obj/{data_key}{sdvxin_id}ult.png"
                )
                bar_url = f"https://sdvx.in/chunithm/ult/bg/{sdvxin_id}bar.png"
            else:
                sdvxin_difficulty = (
                    chart.difficulty.lower() if chart.difficulty != "MAS" else "mst"
                )
                bg_url = (
                    f"https://sdvx.in/chunithm/{sdvxin_id[:2]}/bg/{sdvxin_id}bg.png"
                )
                data_url = f"https://sdvx.in/chunithm/{sdvxin_id[:2]}/obj/{data_key}{sdvxin_id}{sdvxin_difficulty}.png"
                bar_url = (
                    f"https://sdvx.in/chunithm/{sdvxin_id[:2]}/bg/{sdvxin_id}bar.png"
                )

            bg_resp, data_resp, bar_resp = await asyncio.gather(
                self._fetch_sdvxin_with_fallback(
                    chart,
                    bg_url,
                    f"https://sdvx.in/chunithm/{sdvxin_id[:2]}/bg/{sdvxin_id}bg.png",
                ),
                self.http_client.get(data_url),
                self._fetch_sdvxin_with_fallback(
                    chart,
                    bar_url,
                    f"https://sdvx.in/chunithm/{sdvxin_id[:2]}/bg/{sdvxin_id}bar.png",
                ),
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
                f"### {chart_display_name}\n"
                f"BPM: {displayed_bpm}\n"
                f"CHAIN: {chart.maxcombo or '-'} / TAP: {chart.tap or '-'} / HOLD: {chart.hold or '-'} / SLIDE: {chart.slide or '-'} / AIR: {chart.air or '-'} / FLICK: {chart.flick or '-'}\n"
            )

            if chart.charter is not None:
                content += f"NOTES DESIGNER: {escape_markdown(chart.charter)}\n"

            file = discord.File(
                output,
                filename=f"{sdvxin_id}{chart.difficulty.lower()}.jpg",
                description=f"Chart view for {chart_display_name}",
            )

            view = discord.ui.LayoutView(timeout=None)
            jacket_url = get_jacket_url(song)

            view.add_item(
                discord.ui.Container(
                    (
                        discord.ui.Section(
                            discord.ui.TextDisplay(content),
                            accessory=discord.ui.Thumbnail(jacket_url),
                        )
                        if jacket_url is not None
                        else discord.ui.TextDisplay(content)
                    ),
                    discord.ui.MediaGallery(discord.components.MediaGalleryItem(file)),
                    discord.ui.TextDisplay(
                        f"-# {'MIRROR  •  ' if mirror else ''}Chart view by [sdvx.in](https://sdvx.in/chunithm.html)"
                    ),
                    accent_color=difficulty.color(),
                )
            )

            action_row = discord.ui.ActionRow(
                discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label="sdvx.in",
                    url=sdvxin_link(chart.sdvxin_chart_view),
                )
            )

            if yt_url is not None:
                action_row.add_item(
                    discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label="Search on YouTube",
                        url=yt_url,
                    )
                )

            view.add_item(action_row)

            await ctx.respond_or_edit(view=view, files=[file])

    @commands.hybrid_command("codex", aliases=["odex"])
    @logged_prefix_command
    async def odex(self, ctx: Context):
        """Read the Codex."""

        await ctx.reply(
            content=(
                "Read the Codex? Codexes? Codices? It doesn't really matter, just read them.\n"
                "- [Chunithm English Guide](<https://chunithm.org>)\n"
                "- [The (Extended) Chunithm Tutorial](<https://chunithm.org/how-to-improve>)\n"
                "- [Chunithm Chart Compendium/Codex](<https://chunithm.org/codex>)\n"
                "- [Kamaitachi Chunithm Questline](<https://chunithm.org/quests>)\n"
                "- [Linked VERSE Unlock Guide](<https://chunithm.org/linked-verse>)"
            ),
            mention_author=False,
        )

    @commands.hybrid_command("how-to-improve", aliases=["how2improve", "howtoimprove"])
    @logged_prefix_command
    async def how_to_improve(self, ctx: Context):
        await ctx.reply(
            content="[The (Extended) Chunithm Tutorial](https://chunithm.org/how-to-improve)",
            mention_author=False,
        )

    @commands.hybrid_command("roll", extras={"invoke_on_edit": False})
    @logged_prefix_command
    async def roll(
        self,
        ctx: Context,
        max: Range[int, 1] = 100,
    ):
        """Rolls a random number between 1 and the specified maximum.

        Parameters
        ----------
        max: int
            The maximum roll. Must be an integer larger than 1.
        """

        if max > 10**4000 - 1:
            msg = "Maximum roll cannot be larger than 10^4000 - 1 due to Discord character limit."
            raise commands.BadArgument(msg)

        prefix = f"{ctx.author.mention} rolled a "

        # Add 1 since randrange is max-exclusive like range()
        result = self._rng.randrange(1, max + 1)
        content = f"{prefix}{result}"

        if len(content) <= 2000:
            await ctx.reply(content=content, mention_author=False)
        elif len(content) <= 4000 + len(prefix):
            view = discord.ui.LayoutView()

            container = discord.ui.Container()
            view.add_item(container)

            if len(content) <= 4000:
                text_display = discord.ui.TextDisplay(content)
            else:
                text_display = discord.ui.TextDisplay(str(result))

            container.add_item(text_display)

            await ctx.reply(view=view, mention_author=False)
        else:
            msg = "Roll result was too large to fit in a single message. Try a smaller maximum roll."
            raise commands.CommandError(msg)


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
"""  # noqa: RUF001

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
      🟦          😡"""  # noqa: RUF001

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
