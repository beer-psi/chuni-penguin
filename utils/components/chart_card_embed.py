from typing import TYPE_CHECKING, Optional

import discord
from discord.utils import escape_markdown

from chunithm_net.consts import JACKET_BASE
from chunithm_net.entities.enums import Difficulty, Rank
from utils import floor_to_ndp, sdvxin_link, yt_search_link
from utils.calculation.rating import calculate_rating
from utils.ranks import rank_icon

if TYPE_CHECKING:
    from database.models import Chart


class ChartCardEmbed(discord.Embed):
    def __init__(self, chart: "Chart", *, target_score: Optional[int] = None, border: bool = False) -> None:
        difficulty = Difficulty.from_short_form(chart.difficulty)

        super().__init__(
            title=chart.song.title,
            color=difficulty.color(),
            description=escape_markdown(chart.song.artist),
        )

        self.set_thumbnail(url=f"{JACKET_BASE}/{chart.song.jacket}")

        self.add_field(
            name="Category",
            value=chart.song.genre,
        )

        difficulty_display = chart.level
        if chart.const is not None:
            difficulty_display += f" ({chart.const})"

        difficulty_link = yt_search_link(chart.song.title, chart.difficulty)
        if chart.sdvxin_chart_view is not None:
            difficulty_link = sdvxin_link(chart.sdvxin_chart_view.id, chart.difficulty)

        self.add_field(
            name=str(difficulty), value=f"[{difficulty_display}]({difficulty_link})"
        )

        if target_score is not None:
            field_value = str(target_score)

            if chart.const is not None:
                target_rating = calculate_rating(target_score, chart.const)
                field_value += f" ({target_rating:.2f})"

            self.add_field(
                name="Target Score",
                value=field_value,
            )

        if border:
            if chart.maxcombo is not None and chart.maxcombo > 0:
                field_value = str(chart.maxcombo)
                
                tolerance_sssp = floor_to_ndp(chart.maxcombo / 10, 0)
                tolerance_sss = floor_to_ndp(chart.maxcombo / 4, 0)
                tolerance_ssp = floor_to_ndp(chart.maxcombo / 2, 0)
                tolerance_ss = floor_to_ndp(chart.maxcombo, 0)
                tolerance_sp = floor_to_ndp(chart.maxcombo * 2, 0)
                tolerance_s = floor_to_ndp(chart.maxcombo * 3.5, 0)

                border_miss_sssp = 0
                border_miss_sss = 0
                border_miss_ssp = floor_to_ndp(tolerance_ssp / 300, 0)
                border_miss_ss = floor_to_ndp(tolerance_ss / 275, 0)
                border_miss_sp = floor_to_ndp(tolerance_sp / 250, 0)
                border_miss_s = floor_to_ndp(tolerance_s / 200, 0)

                border_atk_sssp = floor_to_ndp(tolerance_sssp / 60, 0) - border_miss_sssp * 2
                border_atk_sss = floor_to_ndp(tolerance_sss / 59, 0) - border_miss_sss * 2
                border_atk_ssp = floor_to_ndp(tolerance_ssp / 58, 0) - border_miss_ssp * 2
                border_atk_ss = floor_to_ndp(tolerance_ss / 56, 0) - border_miss_ss * 2
                border_atk_sp = floor_to_ndp(tolerance_sp / 54, 0) - border_miss_sp * 2
                border_atk_s = floor_to_ndp(tolerance_s / 53, 0) - border_miss_s * 2

                border_jus_sssp = tolerance_sssp - border_atk_sssp * 51 - border_miss_sssp * 101
                border_jus_sss = tolerance_sss - border_atk_sss * 51 - border_miss_sss * 101
                border_jus_ssp = tolerance_ssp - border_atk_ssp * 51 - border_miss_ssp * 101
                border_jus_ss = tolerance_ss - border_atk_ss * 51 - border_miss_ss * 101
                border_jus_sp = tolerance_sp - border_atk_sp * 51 - border_miss_sp * 101
                border_jus_s = tolerance_s - border_atk_s * 51 - border_miss_s * 101

                deduction_jus = floor_to_ndp(10_000 / chart.maxcombo, 2)
                deduction_atk = floor_to_ndp(510_000 / chart.maxcombo, 2)
                deduction_miss = floor_to_ndp(1_010_000 / chart.maxcombo, 2)

                self.add_field(
                    name="Note Count",
                    value=field_value,
                )

                self.add_field(
                    name="Borders (JUSTICE-ATTACK-MISS)",
                    value=(
                        f"▸ {rank_icon(Rank.SSSp)} ▸ {border_jus_sssp:.0f}-{border_atk_sssp:.0f}-{border_miss_sssp:.0f}\n"
                        f"▸ {rank_icon(Rank.SSS)} ▸ {border_jus_sss:.0f}-{border_atk_sss:.0f}-{border_miss_sss:.0f}\n"
                        f"▸ {rank_icon(Rank.SSp)} ▸ {border_jus_ssp:.0f}-{border_atk_ssp:.0f}-{border_miss_ssp:.0f}\n"
                        f"▸ {rank_icon(Rank.SS)} ▸ {border_jus_ss:.0f}-{border_atk_ss:.0f}-{border_miss_ss:.0f}\n"
                        f"▸ {rank_icon(Rank.Sp)} ▸ {border_jus_sp:.0f}-{border_atk_sp:.0f}-{border_miss_sp:.0f}\n"
                        f"▸ {rank_icon(Rank.S)} ▸ {border_jus_s:.0f}-{border_atk_s:.0f}-{border_miss_s:.0f}"
                    ),
                )

                self.add_field(
                    name="Score Deduction",
                    value=(
                        f"▸ JUSTICE: -{deduction_jus:.2f}\n"
                        f"▸ ATTACK: -{deduction_atk:.2f}\n"
                        f"▸ MISS: -{deduction_miss:.2f}"
                    ),
                )

