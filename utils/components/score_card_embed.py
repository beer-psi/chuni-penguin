from typing import Optional

import discord
from discord.utils import escape_markdown

from utils import floor_to_ndp

from ..calculation.overpower import calculate_play_overpower
from ..ranks import rank_icon
from ..types.annotated_records import (
    AnnotatedDetailedRecentRecord,
    AnnotatedMusicRecord,
    AnnotatedRecentRecord,
)


class ScoreCardEmbed(discord.Embed):
    def __init__(
        self,
        record: AnnotatedMusicRecord
        | AnnotatedRecentRecord
        | AnnotatedDetailedRecentRecord,
        *,
        show_clear_type: bool = True,
        index: Optional[int] = None,
    ):
        super().__init__(
            color=record.difficulty.color(),
        )
        self.set_thumbnail(url=record.full_jacket_url())

        if show_clear_type:
            score_data = f"▸ {rank_icon(record.rank)} ▸ {record.clear} ▸ {record.score}"
        else:
            score_data = f"▸ {rank_icon(record.rank)} ▸ {record.score}"

        footer_sections = []
        if record.play_rating is not None:
            play_overpower = calculate_play_overpower(record)
            play_op_display = f"{floor_to_ndp(play_overpower, 2)} ({floor_to_ndp(play_overpower / record.overpower_max * 100, 2)}%)"

            if show_clear_type:
                footer_sections = [
                    f"Rating: {floor_to_ndp(record.play_rating, 2)}",
                    f"OP {play_op_display}",
                ]
            else:
                score_data += f" ▸ **{record.play_rating:.2f}**"
                footer_sections = [f"OP {play_op_display}"]

        if record.play_count is not None:
            footer_sections.append(
                f"{record.play_count} attempt{'s' if record.play_count > 1 else ''}"
            )

        self.set_footer(text="  •  ".join(footer_sections))

        if isinstance(record, AnnotatedDetailedRecentRecord):
            score_data += f" ▸ x{record.max_combo}{f'/{record.full_combo}' if record.full_combo else ''}"

            self.add_field(
                name="\u200B",
                value=(
                    f"CRITICAL {record.judgements.jcrit}\n"
                    f"JUSTICE {record.judgements.justice}\n"
                    f"ATTACK {record.judgements.attack}\n"
                    f"MISS {record.judgements.miss}"
                ),
                inline=True,
            )
            self.add_field(
                name="\u200B",
                value=(
                    f"TAP {record.note_type.tap * 100:.2f}%\n"
                    f"HOLD {record.note_type.hold * 100:.2f}%\n"
                    f"SLIDE {record.note_type.slide * 100:.2f}%\n"
                    f"AIR {record.note_type.air * 100:.2f}%\n"
                    f"FLICK {record.note_type.flick * 100:.2f}%"
                ),
                inline=True,
            )

        if isinstance(record, AnnotatedRecentRecord) or isinstance(
            record, AnnotatedDetailedRecentRecord
        ):
            self.timestamp = record.date

            self.set_author(name=f"TRACK {record.track}")
            self.description = (
                f"**{escape_markdown(record.title)} [{record.displayed_difficulty}]**\n"
                "\n"
                f"{score_data}"
            )
        else:
            name = f"{record.title} [{record.displayed_difficulty}]"
            if index is not None:
                name = f"{index}. {name}"

            self.set_author(name=name)
            self.description = score_data
