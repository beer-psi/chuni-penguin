from typing import TYPE_CHECKING, Optional

import discord
from discord.utils import escape_markdown

from chunithm_net.models.enums import Difficulty
from utils import floor_to_ndp, get_jacket_url, sdvxin_link, yt_search_link
from utils.border import calculate_border, calculate_score_deduction_per_judgement
from utils.calculation.rating import calculate_rating
from utils.ranks import rank_icon

if TYPE_CHECKING:
    from database.models import Chart


class ChartCardEmbed(discord.Embed):
    def __init__(
        self,
        chart: "Chart",
        *,
        target_score: Optional[int] = None,
        border: bool = False,
    ) -> None:
        difficulty = Difficulty.from_short_form(chart.difficulty)

        super().__init__(
            title=chart.song.title,
            color=difficulty.color(),
            description=escape_markdown(chart.song.artist),
        )

        self.set_thumbnail(url=get_jacket_url(chart.song))

        self.add_field(
            name="Category",
            value=chart.song.genre,
        )

        difficulty_display = chart.level
        if chart.const is not None:
            difficulty_display += f" ({chart.const})"

        difficulty_link = yt_search_link(
            chart.song.title, chart.difficulty, chart.level
        )
        if chart.sdvxin_chart_view is not None:
            difficulty_link = sdvxin_link(chart.sdvxin_chart_view)

        self.add_field(
            name=str(difficulty), value=f"[{difficulty_display}]({difficulty_link})"
        )

        if target_score is not None:
            field_value = str(target_score)

            if chart.const is not None:
                target_rating = calculate_rating(target_score, chart.const)
                field_value += f" ({floor_to_ndp(target_rating, 2)})"

            self.add_field(
                name="Target Score",
                value=field_value,
            )

        if border and chart.maxcombo is not None and chart.maxcombo > 0:
            self.add_field(
                name="Note Count",
                value=str(chart.maxcombo),
            )

            borders = calculate_border(chart.maxcombo)
            field_value = ""

            for rank, judgements in borders.items():
                field_value += f"▸ {rank_icon(rank)} ▸ {judgements.justice}-{judgements.attack}-{judgements.miss}\n"

            self.add_field(
                name="Borders (JUSTICE-ATTACK-MISS)",
                value=field_value.strip(),
            )

            deductions = calculate_score_deduction_per_judgement(chart.maxcombo)

            self.add_field(
                name="Score Deduction",
                value=(
                    f"▸ JUSTICE: -{deductions['justice']:.2f}\n"
                    f"▸ ATTACK: -{deductions['attack']:.2f}\n"
                    f"▸ MISS: -{deductions['miss']:.2f}"
                ),
            )
