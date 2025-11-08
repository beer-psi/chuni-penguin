import discord
from discord.utils import escape_markdown

from chuni_penguin.calculation.border import calculate_score_deduction_per_judgement
from chuni_penguin.config import config
from chuni_penguin.networks.consts import (
    KEY_INTERNAL_LEVEL,
    KEY_LEVEL,
    KEY_OVERPOWER,
    KEY_OVERPOWER_MAX,
    KEY_PLAY_RATING,
    KEY_SONG_ID,
    KEY_TOTAL_COMBO,
)
from chuni_penguin.networks.types import (
    ChainLamp,
    ClearLamp,
    ComboLamp,
    Difficulty,
    PersonalBest,
    RecentScore,
    Score,
)
from chuni_penguin.utils import floor_to_ndp


class ScoreCardEmbed(discord.Embed):
    def __init__(
        self,
        record: Score,
        *,
        show_lamps: bool = True,
        index: int | None = None,
        synthesis_alt_jacket: str | None = None,
        detailed: bool = False,
    ):
        super().__init__(color=record.difficulty.color())

        self.set_thumbnail(url=record.jacket_url)

        if record.extras.get(KEY_SONG_ID) == 2698:
            if synthesis_alt_jacket == "none":
                self.set_thumbnail(url=None)
            elif synthesis_alt_jacket != "default" and config.web.serve_assets:
                self.set_thumbnail(
                    url=f"{config.web.base_url}/assets/jackets/2698_{synthesis_alt_jacket}.png"
                )

        if show_lamps:
            lamps: list[ChainLamp | ClearLamp | ComboLamp] = [record.clear_lamp]

            if (
                record.combo_lamp != ComboLamp.none
                or (
                    record.chain_lamp is not None
                    and record.chain_lamp != ChainLamp.none
                )
            ) and record.clear_lamp == ClearLamp.clear:
                lamps = []

            if record.combo_lamp != ComboLamp.none:
                lamps.append(record.combo_lamp)
            if record.chain_lamp is not None and record.chain_lamp != ChainLamp.none:
                lamps.append(record.chain_lamp)

            if len(lamps) > 2:
                lamps_str = [x.short() for x in lamps]
            else:
                lamps_str = [str(x) for x in lamps]

            score_data = f"▸ {config.icons.rank_icon(record.rank)} ▸ {' / '.join(lamps_str)} ▸ {record.score}"
        else:
            score_data = f"▸ {config.icons.rank_icon(record.rank)} ▸ {record.score}"

        footer_sections = []
        if play_rating := record.extras.get(KEY_PLAY_RATING):
            play_overpower = record.extras[KEY_OVERPOWER]
            overpower_max = record.extras[KEY_OVERPOWER_MAX]
            play_op_display = f"{floor_to_ndp(play_overpower, 2)} ({floor_to_ndp(play_overpower / overpower_max * 100, 2)}%)"

            footer_sections = []
            if record.difficulty != Difficulty.worlds_end:
                if show_lamps:
                    footer_sections.append(f"Rating: {floor_to_ndp(play_rating, 2)}")
                else:
                    score_data += f" ▸ **{floor_to_ndp(play_rating, 2)}**"

            if record.difficulty != Difficulty.worlds_end:
                footer_sections.append(f"OP: {play_op_display}")

        if isinstance(record, PersonalBest) and record.play_count is not None:
            footer_sections.append(
                f"{record.play_count} attempt{'s' if record.play_count > 1 else ''}"
            )

        self.set_footer(text="  •  ".join(footer_sections))

        if isinstance(record, PersonalBest) and record.ajc_count is not None:
            score_data += f"\n▸ AJC count: {record.ajc_count}"

        total_combo = record.extras.get(KEY_TOTAL_COMBO)

        if record.max_combo is not None and record.max_combo >= 0:
            score_data += (
                f" ▸ x{record.max_combo}{f'/{total_combo}' if total_combo else ''}"
            )

        has_judgements = record.judgements is not None and (
            record.judgements.justice_critical >= 0
            and record.judgements.justice >= 0
            and record.judgements.attack >= 0
            and record.judgements.miss >= 0
        )

        has_note_percentages = record.note_percentage is not None and (
            record.note_percentage.tap >= 0
            and record.note_percentage.hold >= 0
            and record.note_percentage.slide >= 0
            and record.note_percentage.air >= 0
            and record.note_percentage.flick >= 0
        )

        if has_judgements and has_note_percentages:
            detailed = True

        if detailed:
            if has_judgements:
                assert record.judgements is not None

                if total_combo:
                    deductions = calculate_score_deduction_per_judgement(total_combo)
                    loss_justice = (
                        int(deductions["justice"] * 100) * record.judgements.justice
                    )
                    loss_attack = (
                        int(deductions["attack"] * 100) * record.judgements.attack
                    )
                    loss_miss = int(deductions["miss"] * 100) * record.judgements.miss
                else:
                    deductions = None
                    loss_justice = None
                    loss_attack = None
                    loss_miss = None

                self.add_field(
                    name="\u200b",
                    value=(
                        f"CRITICAL {record.judgements.justice_critical}\n"
                        f"JUSTICE {record.judgements.justice}{f' (-{loss_justice // 100}.{loss_justice % 100:02})' if loss_justice else ''}\n"
                        f"ATTACK {record.judgements.attack}{f' (-{loss_attack // 100}.{loss_attack % 100:02})' if loss_attack else ''}\n"
                        f"MISS {record.judgements.miss}{f' (-{loss_miss // 100}.{loss_miss % 100:02})' if loss_miss else ''}"
                    ),
                    inline=True,
                )

            if has_note_percentages:
                assert record.note_percentage is not None

                self.add_field(
                    name="\u200b",
                    value=(
                        f"TAP {record.note_percentage.tap:.2f}%\n"
                        f"HOLD {record.note_percentage.hold:.2f}%\n"
                        f"SLIDE {record.note_percentage.slide:.2f}%\n"
                        f"AIR {record.note_percentage.air:.2f}%\n"
                        f"FLICK {record.note_percentage.flick:.2f}%"
                    ),
                    inline=True,
                )
        elif has_judgements:
            assert record.judgements is not None

            score_data += "\n"
            score_data += f"▸ {record.judgements.justice_critical} / {record.judgements.justice} / {record.judgements.attack} / {record.judgements.miss}"

        if record.achieved_at is not None and record.achieved_at.timestamp() > 0:
            self._timestamp = record.achieved_at

        if isinstance(record, RecentScore):
            if record.track_no is not None and record.track_no > 0:
                self.set_author(name=f"TRACK {record.track_no}")

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


def _displayed_difficulty(record: Score) -> str:
    difficulty = record.difficulty
    level = record.extras.get(KEY_LEVEL)
    internal_level = record.extras.get(KEY_INTERNAL_LEVEL)

    if internal_level:
        return f"{difficulty} {internal_level}"
    if level != "0" and level:
        return f"{difficulty} {level}"
    return f"{difficulty}"
