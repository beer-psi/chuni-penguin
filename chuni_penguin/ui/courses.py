from collections.abc import Sequence
from math import ceil
from typing import TYPE_CHECKING, Any

import discord
from discord.utils import MISSING, escape_markdown
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import select

from chuni_penguin.config import config
from chuni_penguin.constants import CURRENT_CHUNITHM_VERSION
from chuni_penguin.database import Chart, Course, CourseTrack
from chuni_penguin.networks.types import (
    ClearLamp,
    ComboLamp,
    CourseClass,
    CourseRecord,
    Difficulty,
)
from chuni_penguin.utils import get_jacket_url, sdvxin_link, yt_search_link

from ._base import PenguinLayoutView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot
    from chuni_penguin.context import PenguinContext


def format_life_deduction(num: int):
    if num < 0:
        return f"+{-num}"

    return f"-{num}"


def format_conditions(course: Course):
    parts: list[str] = [f"{course.life} LIFE"]

    if (
        course.damage_miss != 0
        and course.damage_attack == 0
        and course.damage_justice == 0
        and course.damage_jcrit == 0
    ):
        parts.append(f"MISS {format_life_deduction(course.damage_miss)}")
    elif (
        course.damage_miss != 0
        and course.damage_attack == course.damage_miss
        and course.damage_justice == 0
        and course.damage_jcrit == 0
    ):
        parts.append(f"ATTACK and below {format_life_deduction(course.damage_miss)}")
    elif (  # critical justice courses/random courses, all sorts of things
        course.damage_miss != 0
        and course.damage_attack == course.damage_miss
        and course.damage_justice == course.damage_miss
        and course.damage_jcrit == 0
    ):
        parts.append(f"JUSTICE and below {format_life_deduction(course.damage_miss)}")
    elif (  # never used, but hey, just in case
        course.damage_miss != 0
        and course.damage_attack == course.damage_miss
        and course.damage_justice == course.damage_miss
        and course.damage_jcrit == course.damage_miss
    ):
        parts.append(
            f"JUSTICE CRITICAL and below {format_life_deduction(course.damage_miss)}"
        )
    elif (  # usually used for kop course where damage_attack and above is negative
        course.damage_miss != 0
        and course.damage_attack != 0
        and course.damage_justice == course.damage_attack
        and course.damage_jcrit == course.damage_attack
    ):
        parts.append(f"MISS {format_life_deduction(course.damage_miss)}")
        parts.append(f"ATTACK and above {format_life_deduction(course.damage_attack)}")
    else:  # fallback to formatting life deduction for each judgement
        if course.damage_miss != 0:
            parts.append(f"MISS {format_life_deduction(course.damage_miss)}")
        if course.damage_attack != 0:
            parts.append(f"ATTACK {format_life_deduction(course.damage_attack)}")
        if course.damage_justice != 0:
            parts.append(f"JUSTICE {format_life_deduction(course.damage_justice)}")
        if course.damage_jcrit != 0:
            parts.append(
                f"JUSTICE CRITICAL {format_life_deduction(course.damage_jcrit)}"
            )

    if course.recovery_life > 0:
        parts.append(f"+{course.recovery_life} after each track cleared")

    return ", ".join(parts)


def format_chart(chart: Chart):
    content = f"### {escape_markdown(chart.song.title)} [{Difficulty(chart.difficulty)} {chart.const or chart.level}]"

    if chart.song.bpm is not None:
        content += f"\nBPM: {chart.song.bpm}"

        if (
            chart.song.min_bpm is not None
            and chart.song.max_bpm is not None
            and chart.song.min_bpm != chart.song.max_bpm
        ):
            content += f" ({chart.song.min_bpm}~{chart.song.max_bpm})"

    if chart.maxcombo is not None:
        content += f"\nCHAIN: {chart.maxcombo or '-'} / TAP: {chart.tap or '-'} / HOLD: {chart.hold or '-'} / SLIDE: {chart.slide or '-'} / AIR: {chart.air or '-'} / FLICK: {chart.flick or '-'}"

    if chart.charter is not None:
        content += f"\nNOTES DESIGNER: {escape_markdown(chart.charter)}"

    footer_parts: list[str] = []

    if chart.sdvxin_chart_view is not None:
        footer_parts.append(f"[sdvx.in]({sdvxin_link(chart.sdvxin_chart_view)})")

    footer_parts.append(
        f"[Search on YouTube]({yt_search_link(chart.song.title, chart.difficulty)})"
    )

    content += f"\n-# {' • '.join(footer_parts)}"

    return content


def format_course_record(record: CourseRecord):
    lamps: list[str] = []

    if record.clear_lamp != ClearLamp.clear:
        lamps.append(str(record.clear_lamp))

    if record.combo_lamp != ComboLamp.none:
        lamps.append(str(record.combo_lamp))

    if len(lamps) == 0:
        lamps = ["CLEAR"]

    return f"▸ {config.icons.rank_icon(record.rank)} ▸ {' / '.join(lamps)} ▸ {record.score}"


def format_course_heading(
    course: Course,
    record: CourseRecord | None,
    level: int = 3,
    *,
    show_version: bool = False,
):
    course_heading = f"{'#' * level} {course.name}"

    if show_version:
        course_heading += f"\nCHUNITHM {course.version} - CLASS {course.cls}"

    course_heading += f"\n{format_conditions(course)}"

    if not course.is_duplicate_track_allowed:
        course_heading += "\nRandom tracks are guaranteed to not repeat."

    if record is not None:
        course_heading += f"\n{format_course_record(record)}"

    return course_heading


class CourseViewSongsButton(discord.ui.Button):
    def __init__(self, course: Course):
        self.course = course

        super().__init__(style=discord.ButtonStyle.primary, label="Songs")

    async def callback(self, interaction: discord.Interaction["ChuniBot"]) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        assert isinstance(self.view, CourseListView)

        back_to_list = discord.ui.Button(label="Back")
        back_to_list.callback = self.view._update_course_list

        self.view.container.clear_items()
        self.view.container.add_item(
            discord.ui.TextDisplay(
                format_course_heading(
                    self.course,
                    self.view.course_records_by_id.get(self.course.id),
                    level=2,
                    show_version=True,
                )
            )
        )

        for track in self.course.tracks.values():
            self.view.container.add_item(discord.ui.Separator())

            if track.level is not None:
                self.view.container.add_item(
                    discord.ui.Section(
                        discord.ui.TextDisplay(f"### RANDOM\nLevel {track.level}"),
                        accessory=discord.ui.Thumbnail(
                            "https://chunithm-net-eng.com/mobile/images/course_r.png"
                        ),
                    )
                )
            elif len(track.charts) == 1:
                chart = track.charts[0]
                jacket_url = get_jacket_url(chart.song)

                if jacket_url is not None:
                    self.view.container.add_item(
                        discord.ui.Section(
                            discord.ui.TextDisplay(format_chart(chart)),
                            accessory=discord.ui.Thumbnail(jacket_url),
                        )
                    )
                else:
                    self.view.container.add_item(
                        discord.ui.TextDisplay(format_chart(chart))
                    )
            elif len(track.charts) > 1:
                chart_list: list[str] = []

                for chart in track.charts:
                    difficulty = Difficulty(chart.difficulty)
                    displayed_difficulty = (
                        f"[{difficulty} {chart.const or chart.level}]"
                    )

                    if chart.sdvxin_chart_view is not None:
                        displayed_difficulty = f"[{displayed_difficulty}]({sdvxin_link(chart.sdvxin_chart_view)})"
                    else:
                        displayed_difficulty = f"[{displayed_difficulty}]({yt_search_link(chart.song.title, str(difficulty))})"

                    chart_list.append(f"▸ {chart.song.title} {displayed_difficulty}")

                self.view.container.add_item(
                    discord.ui.Section(
                        discord.ui.TextDisplay("### RANDOM\n" + "\n".join(chart_list)),
                        accessory=discord.ui.Thumbnail(
                            "https://chunithm-net-eng.com/mobile/images/course_r.png"
                        ),
                    )
                )
            else:
                self.view.container.add_item(discord.ui.TextDisplay("No information."))

        self.view.container.add_item(discord.ui.Separator())
        self.view.container.add_item(
            discord.ui.Section(
                discord.ui.TextDisplay("Back to course list"), accessory=back_to_list
            )
        )

        await self.view.edit_message(interaction)


class CourseListView(PenguinLayoutView):
    container = discord.ui.Container(
        discord.ui.TextDisplay("## Course List"),
        discord.ui.TextDisplay("Select a course class to view courses."),
        accent_color=discord.Color.yellow(),
    )
    version_action_row = discord.ui.ActionRow()
    class_action_row = discord.ui.ActionRow()
    pagination_action_row = discord.ui.ActionRow()

    def __init__(
        self,
        ctx: "PenguinContext",
        version_groups: Sequence[Sequence[str]],
        course_records: list[CourseRecord] = MISSING,
        version_selected: str = MISSING,
        class_selected: CourseClass = MISSING,
        *,
        timeout: float | None = 300.0,
    ):
        super().__init__(ctx, timeout=timeout)

        self.course_records_by_id = (
            {r.id: r for r in course_records} if course_records is not MISSING else {}
        )
        self.version_group_selected = 0

        self.ctx = ctx
        self.version_groups = version_groups

        version = (
            version_selected
            if version_selected is not MISSING
            else CURRENT_CHUNITHM_VERSION
        )

        for i, version_group in enumerate(version_groups):
            default = False

            if version in version_group:
                default = True
                self.version_group_selected = i

            self.version_select.options.append(
                discord.SelectOption(
                    label=version_group[0], value=str(i), default=default
                )
            )

        self.class_select.options = [
            discord.SelectOption(
                label=f"CLASS {cls}",
                value=str(cls.value),
                default=class_selected == cls,
            )
            for cls in CourseClass
        ]
        self.courses: list[Course] = []

        self._current_page: int = 0
        self.remove_item(self.pagination_action_row)
        self._pagination_displayed: bool = False

    @property
    def current_page(self):
        return self._current_page

    @current_page.setter
    def current_page(self, value: int):
        self._current_page = value
        self._update_labels(self._current_page)

    def _update_labels(self, page_index: int):
        max_pages = ceil(len(self.courses) / 5)

        if max_pages is not None:
            self.jump_to_page.label = f"{page_index + 1}/{max_pages}"
        else:
            self.jump_to_page.label = f"{page_index + 1}"

        self.to_first_page.disabled = page_index == 0
        self.to_previous_page.disabled = page_index == 0
        self.to_next_page.disabled = (
            max_pages is not None and (page_index + 1) >= max_pages
        )
        self.to_last_page.disabled = max_pages is None or (page_index + 1) >= max_pages

    @version_action_row.select(placeholder="Select a version...")
    async def version_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        await self._update_course_list(interaction)

    @class_action_row.select(placeholder="Select a course class...")
    async def class_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        await self._update_course_list(interaction)

    @pagination_action_row.button(
        label="<<", style=discord.ButtonStyle.grey, disabled=True
    )
    async def to_first_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.show_page(interaction, 0)

    @pagination_action_row.button(
        label="<", style=discord.ButtonStyle.grey, disabled=True
    )
    async def to_previous_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.show_page(interaction, max(self.current_page - 1, 0))

    @pagination_action_row.button(
        label="...", style=discord.ButtonStyle.grey, disabled=True
    )
    async def jump_to_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        pass

    @pagination_action_row.button(label=">", style=discord.ButtonStyle.grey)
    async def to_next_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        max_pages = ceil(len(self.courses) / 5)

        if max_pages is not None:
            await self.show_page(interaction, min(self.current_page + 1, max_pages - 1))
        else:
            await self.show_page(interaction, self.current_page + 1)

    @pagination_action_row.button(label=">>", style=discord.ButtonStyle.grey)
    async def to_last_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        max_pages = ceil(len(self.courses) / 5)

        # this should always happen since this button only shows up if there's a max page.
        if max_pages is not None:
            await self.show_page(interaction, max_pages - 1)

    async def show_page(self, interaction: discord.Interaction, page_index: int):
        self.current_page = page_index
        version_group_idx = (
            int(self.version_select.values[0])  # pyright: ignore[reportAttributeAccessIssue]
            if len(self.version_select.values) > 0  # pyright: ignore[reportAttributeAccessIssue]
            else self.version_group_selected
        )
        cls = CourseClass(int(self.class_select.values[0]))

        for option in self.version_select.options:
            option.default = option.value == str(version_group_idx)

        for option in self.class_select.options:
            option.default = option.value == str(cls.value)

        await self._display_courses(
            interaction,
            " / ".join(self.version_groups[version_group_idx]),
            cls,
            self.courses[5 * page_index : 5 * (page_index + 1)],
        )

    async def _update_course_list(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

        if len(self.class_select.values) <= 0:
            return

        version_group_idx = (
            int(self.version_select.values[0])  # pyright: ignore[reportAttributeAccessIssue]
            if len(self.version_select.values) > 0  # pyright: ignore[reportAttributeAccessIssue]
            else self.version_group_selected
        )
        cls = CourseClass(int(self.class_select.values[0]))

        for option in self.version_select.options:
            option.default = option.value == str(version_group_idx)

        for option in self.class_select.options:
            option.default = option.value == str(cls.value)

        async with self.ctx.bot.begin_db_read() as session:
            query = (
                select(Course)
                .where(
                    Course.version.in_(self.version_groups[version_group_idx])
                    & (Course.cls == cls)
                )
                .options(
                    joinedload(Course.tracks)
                    .joinedload(CourseTrack.charts)
                    .options(
                        joinedload(Chart.song), joinedload(Chart.sdvxin_chart_view)
                    )
                )
            )
            self.courses = list((await session.execute(query)).scalars().unique())

        self.current_page = 0

        if not self._pagination_displayed and len(self.courses) > 5:
            self.add_item(self.pagination_action_row)
            self._pagination_displayed = True
        elif self._pagination_displayed and len(self.courses) <= 5:
            self.remove_item(self.pagination_action_row)
            self._pagination_displayed = False

        await self._display_courses(
            interaction,
            " / ".join(self.version_groups[version_group_idx]),
            cls,
            self.courses[:5],
        )

    async def _display_courses(
        self,
        interaction: discord.Interaction,
        version: str,
        course_class: CourseClass,
        courses: list[Course],
    ):
        heading = discord.ui.TextDisplay(
            f"## Course List\n{version} - CLASS {course_class}"
        )
        self.container.clear_items()
        self.container.add_item(heading)

        if len(courses) == 0:
            heading.content += "\nNo courses found."

            await self.edit_message(interaction)
            return

        for course in courses:
            self.container.add_item(discord.ui.Separator())
            self.container.add_item(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        format_course_heading(
                            course, self.course_records_by_id.get(course.id)
                        )
                    ),
                    accessory=CourseViewSongsButton(course),
                )
            )

        await self.edit_message(interaction)
