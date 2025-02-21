from typing import Optional

import discord
from discord.utils import escape_markdown

from chunithm_net.consts import (
    KEY_INTERNAL_LEVEL,
    KEY_LEVEL,
    KEY_OVERPOWER_MAX,
    KEY_PLAY_RATING,
    KEY_TOTAL_COMBO,
)
from chunithm_net.models.enums import ChainType, ClearType, ComboType, Difficulty
from chunithm_net.models.record import (
    DetailedRecentRecord,
    MusicRecord,
    RecentRecord,
    Record,
)
from utils import floor_to_ndp
from utils.calculation.overpower import calculate_play_overpower
from utils.ranks import rank_icon


class ScoreCardEmbed(discord.Embed):
    def __init__(
        self,
        record: Record,
        *,
        show_lamps: bool = True,
        index: Optional[int] = None,
    ):
        super().__init__(
            color=record.difficulty.color(),
        )
        self.set_thumbnail(url=record.jacket)

        if show_lamps:
            lamps: list[ChainType | ClearType | ComboType] = [record.clear_lamp]

            if record.combo_lamp != ComboType.NONE:
                lamps.append(record.combo_lamp)
            if record.chain_lamp != ChainType.NONE:
                lamps.append(record.chain_lamp)

            if len(lamps) > 2:
                lamps_str = [x.short_form() for x in lamps]
            else:
                lamps_str = [str(x) for x in lamps]

            score_data = (
                f"▸ {rank_icon(record.rank)} ▸ {' / '.join(lamps_str)} ▸ {record.score}"
            )
        else:
            score_data = f"▸ {rank_icon(record.rank)} ▸ {record.score}"

        footer_sections = []
        if play_rating := record.extras.get(KEY_PLAY_RATING):
            play_overpower = calculate_play_overpower(record)
            overpower_max = record.extras[KEY_OVERPOWER_MAX]
            play_op_display = f"{floor_to_ndp(play_overpower, 2)} ({floor_to_ndp(play_overpower / overpower_max * 100, 2)}%)"

            footer_sections = []
            if record.difficulty != Difficulty.WORLDS_END:
                if show_lamps:
                    footer_sections.append(f"Rating: {floor_to_ndp(play_rating, 2)}")
                else:
                    score_data += f" ▸ **{floor_to_ndp(play_rating, 2)}**"

            if record.difficulty != Difficulty.WORLDS_END:
                footer_sections.append(f"OP: {play_op_display}")

        if isinstance(record, MusicRecord) and record.play_count is not None:
            footer_sections.append(
                f"{record.play_count} attempt{'s' if record.play_count > 1 else ''}"
            )

        self.set_footer(text="  •  ".join(footer_sections))

        if isinstance(record, MusicRecord) and record.ajc_count is not None:
            score_data += f"\n▸ AJC count: {record.ajc_count}"

        if isinstance(record, DetailedRecentRecord):
            total_combo = record.extras.get(KEY_TOTAL_COMBO)

            if record.max_combo >= 0:
                score_data += (
                    f" ▸ x{record.max_combo}{f'/{total_combo}' if total_combo else ''}"
                )

            has_judgements = (
                record.judgements.jcrit >= 0
                and record.judgements.justice >= 0
                and record.judgements.attack >= 0
                and record.judgements.miss >= 0
            )

            has_note_percentages = (
                record.note_type.tap >= 0
                and record.note_type.hold >= 0
                and record.note_type.slide >= 0
                and record.note_type.air >= 0
                and record.note_type.flick >= 0
            )

            if has_judgements and has_note_percentages:
                self.add_field(
                    name="\u200b",
                    value=(
                        f"CRITICAL {record.judgements.jcrit}\n"
                        f"JUSTICE {record.judgements.justice}\n"
                        f"ATTACK {record.judgements.attack}\n"
                        f"MISS {record.judgements.miss}"
                    ),
                    inline=True,
                )

                self.add_field(
                    name="\u200b",
                    value=(
                        f"TAP {record.note_type.tap * 100:.2f}%\n"
                        f"HOLD {record.note_type.hold * 100:.2f}%\n"
                        f"SLIDE {record.note_type.slide * 100:.2f}%\n"
                        f"AIR {record.note_type.air * 100:.2f}%\n"
                        f"FLICK {record.note_type.flick * 100:.2f}%"
                    ),
                    inline=True,
                )
            elif has_judgements:
                score_data += "\n"
                score_data += f"▸ {record.judgements.jcrit} / {record.judgements.justice} / {record.judgements.attack} / {record.judgements.miss}"

        if isinstance(record, RecentRecord):
            if record.date.timestamp() > 0:
                self._timestamp = record.date

            if record.track > 0:
                self.set_author(name=f"TRACK {record.track}")

            self.description = (
                f"**{escape_markdown(record.title)} [{_displayed_difficulty(record)}]**\n"
                "\n"
                f"{score_data}"
            )
        else:
            name = f"{record.title} [{_displayed_difficulty(record)}]"
            if index is not None:
                name = f"{index}. {name}"

            self.set_author(name=name)
            self.description = score_data


def _displayed_difficulty(record: Record) -> str:
    difficulty = record.difficulty
    level = record.extras.get(KEY_LEVEL)
    internal_level = record.extras.get(KEY_INTERNAL_LEVEL)

    if internal_level:
        return f"{difficulty} {internal_level}"
    if level != "0" and level:
        return f"{difficulty} {level}"
    return f"{difficulty}"
