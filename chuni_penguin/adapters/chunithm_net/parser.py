# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false, reportArgumentType=false
import calendar
import logging
import re
from pathlib import Path
from typing import cast

import msgspec
from discord.utils import MISSING
from selectolax.lexbor import LexborHTMLParser, LexborNode

from chuni_penguin.types import (
    ChainLamp,
    Chart,
    ClearLamp,
    ComboLamp,
    CourseClass,
    CourseRecord,
    Currency,
    DailyBonus,
    Judgements,
    Leaderboard,
    LeaderboardEntry,
    LinkedGate,
    LinkedGateLeaderboard,
    LinkedGateLeaderboardEntry,
    LinkedGateStatus,
    LinkLevel,
    LoginBonus,
    LoginBonusItem,
    MonthlyLoginBonus,
    NotePercentage,
    OverPower,
    PersonalBest,
    PlayerCollections,
    Possession,
    Profile,
    Rank,
    RatingSystem,
    RatingType,
    RecentScore,
    Skill,
    SkillClass,
    Song,
    Team,
    TeamEmblem,
    Title,
    TitleRarity,
    UserAvatar,
)
from chuni_penguin.types.ranking import (
    CurrencyRanking,
    CurrencyRankingEntry,
    RankingDelta,
    RatingRanking,
    RatingRankingEntry,
    ScoreRanking,
    ScoreRankingEntry,
    TeamRanking,
    TeamRankingEntry,
)

from .consts import LINKED_VERSE_PROGRESS_BADGES
from .utils import (
    chuni_int,
    difficulty_from_imgurl,
    extract_last_part,
    get_course_rank_and_lamps,
    get_rank_and_lamps,
    parse_player_rating,
    parse_time,
)

_logger = logging.getLogger(__name__)

RE_CSS_BACKGROUND_IMAGE = re.compile(
    r"background-image\s*:\s*url\(['\"]?(?P<url>.+?)['\"]?\)"
)


class SpecialTitle(msgspec.Struct):
    content: str
    rarity: str


with (Path(__file__).parent / "assets" / "titles.json").open(encoding="utf-8") as f:
    SPECIAL_TITLES = msgspec.json.decode(f.read(), type=dict[str, SpecialTitle])


def parse_avatar(avatar_group: LexborNode) -> UserAvatar:
    return UserAvatar(
        base="https://new.chunithm-net.com/chuni-mobile/html/mobile/images/avatar_base.png",
        back=avatar_group.css_first(".avatar_back img").attrs["src"],
        skinfoot_r=avatar_group.css_first(".avatar_skinfoot_r img").attrs["src"],
        skinfoot_l=avatar_group.css_first(".avatar_skinfoot_l img").attrs["src"],
        skin=avatar_group.css_first(".avatar_skin img").attrs["src"],
        wear=avatar_group.css_first(".avatar_wear img").attrs["src"],
        face=avatar_group.css_first(".avatar_face img").attrs["src"],
        face_cover=avatar_group.css_first(".avatar_faceCover img").attrs["src"],
        head=avatar_group.css_first(".avatar_head img").attrs["src"],
        hand_r=avatar_group.css_first(".avatar_hand_r img").attrs["src"],
        hand_l=avatar_group.css_first(".avatar_hand_l img").attrs["src"],
        item_r=avatar_group.css_first(".avatar_item_r img").attrs["src"],
        item_l=avatar_group.css_first(".avatar_item_l img").attrs["src"],
        front=avatar_group.css_first(".avatar_front img").attrs["src"],
    )


def parse_title(element: LexborNode) -> Title | None:
    title_style = element.attrs.get("style")

    if title_style is None:
        return None

    title_background_url_match = RE_CSS_BACKGROUND_IMAGE.search(str(title_style))

    if title_background_url_match is None:
        return None

    title_background_url: str = title_background_url_match.group("url")
    title_background_filename = title_background_url.split("/")[-1]

    if title_background_filename.startswith("honor_bg_"):
        title_rarity = title_background_filename.split(".")[0][9:]

        if title_rarity == "noSet":
            return None

        title_content_elem = element.css_first(
            ".player_honor_text span, .honor_now_text span"
        )

        if title_content_elem is None:
            msg = "Invalid title (missing title content on normal titles)"
            raise ValueError(msg)

        title_content = title_content_elem.text()
        title_rarity = TitleRarity(title_rarity)
    elif special_title := SPECIAL_TITLES.get(title_background_filename):
        title_content = special_title.content
        title_rarity = TitleRarity(special_title.rarity)
    else:
        _logger.warning(
            "Ignoring unknown special title with URL %s", title_background_url
        )
        return None

    return Title(content=title_content, rarity=title_rarity)


def parse_player_card_and_avatar(soup: LexborHTMLParser | LexborNode):
    if (e := soup.css_first(".player_chara")) is not None:
        img = e.css_first("img")
        character = img.attrs["src"] if e else None

        character_frame = (
            extract_last_part(e.attrs["style"]) if "style" in e.attrs else None
        )
    else:
        character = None
        character_frame = None

    name_elem = soup.css_first(".player_name_in")

    if (form_elem := name_elem.css_first("form")) is not None:
        name = form_elem.css_first("a").text()
        friend_code = form_elem.css_first("input[name=idx]").attrs["value"]
    else:
        name = name_elem.text()
        friend_code = None

    lv = chuni_int(soup.css_first(".player_lv").text())

    team_name_elem = soup.css_first(".player_team_name")
    team_name = team_name_elem.text() if team_name_elem else None

    team_emblem_elem = soup.css_first(
        ".player_team_emblem_normal, .player_team_emblem_silver, .player_team_emblem_gold, .player_team_emblem_rainbow, .player_team_emblem_purple, .player_team_emblem_red, .player_team_emblem_yellow, .player_team_emblem_green"
    )
    team_emblem = (
        TeamEmblem(extract_last_part(team_emblem_elem.attrs["class"]))
        if team_emblem_elem
        else None
    )

    if team_name and team_emblem:
        team = Team(name=team_name, emblem=team_emblem)
    else:
        team = None

    title_elements = soup.css(".player_honor_short")
    titles: list[Title] = [
        title for elem in title_elements if (title := parse_title(elem)) is not None
    ]

    rating = parse_player_rating(soup.css(".player_rating_num_block img"))

    overpower = soup.css_first(".player_overpower_text").text().split(" ")
    overpower_value = float(overpower[0])
    overpower_progress = float(
        overpower[1].replace("(", "").replace(")", "").replace("%", "")
    )

    last_play_date_str = soup.css_first(".player_lastplaydate_text").text()
    last_play_date = parse_time(last_play_date_str)

    reborn_elem = soup.css_first(".player_reborn")
    reborn = chuni_int(reborn_elem.text()) if reborn_elem else 0

    possession_elem = soup.css_first(".box_playerprofile")
    possession = (
        Possession(extract_last_part(possession_elem.attrs["style"]))  # type: ignore[reportGeneralTypeIssues]
        if possession_elem and "style" in possession_elem.attrs
        else Possession.none
    )

    classemblem_base_elem = soup.css_first(".player_classemblem_base img")
    emblem = (
        SkillClass(
            chuni_int(extract_last_part(classemblem_base_elem.attrs["src"]))  # type: ignore[reportGeneralTypeIssues]
        )
        if classemblem_base_elem and "src" in classemblem_base_elem.attrs
        else None
    )

    classemblem_top_elem = soup.css_first(".player_classemblem_top img")
    medal = (
        SkillClass(
            chuni_int(extract_last_part(classemblem_top_elem.attrs["src"]))  # type: ignore[reportGeneralTypeIssues]
        )
        if classemblem_top_elem and "src" in classemblem_top_elem.attrs
        else None
    )

    avatar_group = soup.css_first(".avatar_group")
    avatar = parse_avatar(avatar_group) if avatar_group is not None else None

    return Profile(
        username=name,
        titles=titles,
        team=team,
        profile_picture=character,
        profile_picture_frame=(
            f"https://chunithm-net-eng.com/mobile/images/charaframe_{character_frame}.png"
            if character_frame
            else None
        ),
        medal=medal,
        emblem=emblem,
        reincarnation_stars=reborn,
        level=lv,
        rating_systems=[RatingSystem(type=RatingType.in_game, value=rating)],
        over_power=OverPower(value=overpower_value, percentage=overpower_progress),
        possession=possession,
        last_played=last_play_date,
        friend_code=friend_code,
        user_avatar=avatar,
    )


def parse_player_data(soup: LexborHTMLParser) -> Profile:
    data = parse_player_card_and_avatar(soup)

    owned_currency = chuni_int(
        soup.css_first(".user_data_point .user_data_text").text()
    )
    total_currency = chuni_int(
        soup.css_first(".user_data_total_point .user_data_text").text()
    )
    data.currency = Currency(owned_currency, total_currency)

    playcount = chuni_int(
        soup.css_first(".user_data_play_count .user_data_text").text()
    )
    data.total_credits = playcount

    data.friend_code = soup.css_first(
        ".user_data_friend_code .user_data_text span:not(.font_90)"
    ).text()

    return data


def parse_basic_recent_record(record: LexborNode) -> RecentScore:
    idx_elem = record.css_first("form input[name=idx]")

    assert idx_elem is not None

    idx = int(cast(str, idx_elem.attrs["value"]))

    date = parse_time((record.css_first(".play_datalist_date, .box_inner01")).text())
    jacket_elem = record.css_first(".play_jacket_img img")
    if (jacket := jacket_elem.attrs.get("data-original")) is None:
        jacket = cast(str, jacket_elem.attrs["src"])
    track = int(record.css_first(".play_track_text").text().split(" ")[1])
    title = record.css_first(".play_musicdata_title").text()

    score = int(record.css_first(".play_musicdata_score_text").text().replace(",", ""))
    new_record = record.css_first(".play_musicdata_score_img") is not None

    if (rank_elem := record.css_first(".play_musicdata_icon")) is not None:
        rank, clear_lamp, combo_lamp, chain_lamp = get_rank_and_lamps(rank_elem)
    else:
        rank = Rank.d
        clear_lamp = ClearLamp.failed
        combo_lamp = ComboLamp.none
        chain_lamp = ChainLamp.none

    song = Song(id=MISSING, title=title, jacket_url=jacket)
    chart = Chart(
        difficulty=difficulty_from_imgurl(
            cast(str, record.css_first(".play_track_result img").attrs["src"])
        )
    )

    return RecentScore(
        song=song,
        chart=chart,
        score=score,
        rank=rank,
        clear_lamp=clear_lamp,
        combo_lamp=combo_lamp,
        chain_lamp=chain_lamp,
        achieved_at=date,
        track_no=track,
        is_new_record=new_record,
        _memo=idx,
    )


def parse_music_record(soup: LexborHTMLParser, song_id: int) -> list[PersonalBest]:
    jacket = (
        str(elem.attrs["src"])
        if (elem := soup.css_first(".play_jacket_img img"))
        else ""
    )
    title = (
        elem.text(strip=True)
        if (
            elem := soup.css_first(
                ".play_musicdata_title, .play_musicdata_worldsend_title"
            )
        )
        else ""
    )
    records = []
    for block in soup.css(".music_box"):
        if (musicdata := block.css_first(".play_musicdata_icon")) is not None:
            rank, clear_lamp, combo_lamp, chain_lamp = get_rank_and_lamps(musicdata)
        else:
            rank = Rank.d
            clear_lamp = ClearLamp.failed
            combo_lamp = ComboLamp.none
            chain_lamp = ChainLamp.none

        song = Song(id=song_id, title=title, jacket_url=jacket)
        chart = Chart(difficulty=difficulty_from_imgurl(block.attrs["class"]))

        score = PersonalBest(
            song=song,
            chart=chart,
            score=chuni_int(
                elem.text()
                if (elem := block.css_first(".musicdata_score_num .text_b")) is not None
                else "0"
            ),
            rank=rank,
            clear_lamp=clear_lamp,
            combo_lamp=combo_lamp,
            chain_lamp=chain_lamp,
            play_count=chuni_int(
                elem.text().replace("times", "")
                if (
                    elem := block.css_first(
                        ".musicdata_score_num .text_b:lexbor-contains(times), .music_box .block_icon_text span:not([class])"
                    )
                )
                is not None
                else "0"
            ),
            ajc_count=chuni_int(elem.text())
            if (elem := block.css_first(".musicdata_score_theory_num")) is not None
            else None,
        )

        records.append(score)

    return records


def parse_music_for_rating(soup: LexborHTMLParser) -> list[PersonalBest]:
    records = []
    for x in soup.css("form:has(.w388.musiclist_box)"):
        if (score_elem := x.css_first(".play_musicdata_highscore .text_b")) is None:
            continue

        if (musicdata := x.css_first(".play_musicdata_icon")) is not None:
            rank, clear_lamp, combo_lamp, chain_lamp = get_rank_and_lamps(musicdata)
        else:
            rank = Rank.d
            clear_lamp = ClearLamp.failed
            combo_lamp = ComboLamp.none
            chain_lamp = ChainLamp.none

        div = x.css_first(".w388.musiclist_box")
        song = Song(
            id=int(str(x.css_first("form input[name=idx]").attrs["value"])),
            title=x.css_first(".music_title, .musiclist_worldsend_title").text(),
        )
        chart = Chart(difficulty=difficulty_from_imgurl(div.attrs["class"]))
        score = PersonalBest(
            song=song,
            chart=chart,
            score=chuni_int(score_elem.text()),
            rank=rank,
            clear_lamp=clear_lamp,
            combo_lamp=combo_lamp,
            chain_lamp=chain_lamp,
        )

        records.append(score)
    return records


def parse_detailed_recent_record(soup: LexborHTMLParser) -> RecentScore:
    def get_judgement_count(class_name):
        return chuni_int(soup.css_first(class_name).text().replace(",", ""))

    def get_note_percentage(class_name):
        return float(soup.css_first(class_name).text().replace("%", ""))

    record = parse_basic_recent_record(soup.css_first(".frame01_inside"))

    record.max_combo = chuni_int(
        soup.css_first(".play_data_detail_maxcombo_block").text()
    )

    jcrit = get_judgement_count(".text_critical.play_data_detail_judge_text")
    justice = get_judgement_count(".text_justice.play_data_detail_judge_text")
    attack = get_judgement_count(".text_attack.play_data_detail_judge_text")
    miss = get_judgement_count(".text_miss.play_data_detail_judge_text")
    record.judgements = Judgements(
        justice_critical=jcrit, justice=justice, attack=attack, miss=miss
    )

    tap = get_note_percentage(".text_tap_red.play_data_detail_notes_text")
    hold = get_note_percentage(".text_hold_yellow.play_data_detail_notes_text")
    slide = get_note_percentage(".text_slide_blue.play_data_detail_notes_text")
    air = get_note_percentage(".text_air_green.play_data_detail_notes_text")
    flick = get_note_percentage(".text_flick_skyblue.play_data_detail_notes_text")
    record.note_percentage = NotePercentage(
        tap=tap, hold=hold, slide=slide, air=air, flick=flick
    )

    record.character = soup.css_first(".play_data_chara_name").text()

    skill_name = soup.css_first(".play_data_skill_name").text()
    record.skill = Skill(name=skill_name, grade=None)

    if skill_grade := soup.css_first(".play_data_skill_grade"):
        record.skill.grade = chuni_int(skill_grade.text())

    record.skill_result = chuni_int(
        soup.css_first(".play_musicdata_skilleffect_text").text().replace("+", "")
    )
    record.song.id = int(str(soup.css_first("form input[name=idx]").attrs["value"]))
    return record


def parse_course_list(soup: LexborHTMLParser):
    courses: list[CourseRecord] = []

    for x in soup.css("form:has(.w388.musiclist_box)"):
        if (score_elem := x.css_first(".play_musicdata_highscore .text_b")) is None:
            continue

        if (musicdata_icon := x.css_first(".play_musicdata_icon")) is not None:
            rank, clear_lamp, combo_lamp = get_course_rank_and_lamps(musicdata_icon)
        else:
            rank = Rank.d
            clear_lamp = ClearLamp.failed
            combo_lamp = ComboLamp.none

        cls = extract_last_part(x.css_first(".w388.musiclist_box").attrs["class"])

        if cls == "class10":
            course_cls = CourseClass.i
        elif cls == "class11":
            course_cls = CourseClass.ii
        elif cls == "class12":
            course_cls = CourseClass.iii
        elif cls == "class13":
            course_cls = CourseClass.iv
        elif cls == "class14":
            course_cls = CourseClass.v
        elif cls == "class20":
            course_cls = CourseClass.infinite
        elif cls == "class22":
            course_cls = CourseClass.extra
        else:
            msg = f"Unknown course class: {cls}"
            raise ValueError(msg)

        course = CourseRecord(
            id=int(x.css_first("form input[name=idx]").attrs["value"]),
            cls=course_cls,
            name=x.css_first(".music_title").text(),
            score=chuni_int(score_elem.text()),
            rank=rank,
            clear_lamp=clear_lamp,
            combo_lamp=combo_lamp,
        )

        courses.append(course)

    return courses


def parse_collection_customize(soup: LexborHTMLParser) -> PlayerCollections:
    titles: list[Title] = [
        title
        for elem in soup.css(".honor_now")
        if (title := parse_title(elem)) is not None
    ]

    return PlayerCollections(
        avatar=parse_avatar(soup.css_first(".avatar_customise_group")),
        titles=titles,
        nameplate=soup.css_first(".nameplate_now img").attrs["src"],
        map_icon=soup.css_first(".mapicon_now img").attrs["src"],
        system_voice=soup.css_first(".systemvoice_now img").attrs["src"],
    )


WEEKDAY_MAP = {
    "Mon.": calendar.MONDAY,
    "Tue.": calendar.TUESDAY,
    "Wed.": calendar.WEDNESDAY,
    "Thu.": calendar.THURSDAY,
    "Fri.": calendar.FRIDAY,
    "Sat.": calendar.SATURDAY,
    "Sun.": calendar.SUNDAY,
}


def parse_login_bonus(soup: LexborHTMLParser) -> LoginBonus:
    login_bonus_status = soup.css_first(
        r':lexbor-contains("Today\'s Login Bonus")'
    ).text()
    received_bonus_today = "Not achieved" not in login_bonus_status

    monthly_bonuses: list[MonthlyLoginBonus] = []

    for monthly_bonus_elem in soup.css(".frame01_inside > div > div.w420"):
        monthly_login_bonus_name = (
            monthly_bonus_elem.css_first(".box01_title").text().strip()
        )

        monthly_days_logged_in: int = 0

        for e in monthly_bonus_elem.css(
            ".monthly_cumulative_login_bonus_days_count_num img"
        ):
            digit = extract_last_part(e.attrs["src"])
            monthly_days_logged_in = monthly_days_logged_in * 10 + int(digit)

        monthly_login_bonus_rewards: list[LoginBonusItem] = []

        for e in monthly_bonus_elem.css(
            ".monthly_cumulative_login_bonus_reward, .monthly_cumulative_login_bonus_reward_off"
        ):
            bonus_days_block = e.css_first(".bonus_days_block")

            if bonus_days_block is None:
                continue

            day = chuni_int(bonus_days_block.text().removeprefix("Day "))
            icon_url = e.css_first(
                ".monthly_cumulative_login_bonus_reward_img img"
            ).attrs["src"]
            name = e.css_first(".bonus_reward_honor_text").text().strip()
            obtained = (
                e.css_first(".monthly_cumulative_login_bonus_reward_get") is not None
            )

            monthly_login_bonus_rewards.append(
                LoginBonusItem(
                    day=day,
                    icon_url=icon_url,
                    name=name,
                    obtained=obtained,
                )
            )

        monthly_bonuses.append(
            MonthlyLoginBonus(
                name=monthly_login_bonus_name,
                days_logged_in=monthly_days_logged_in,
                rewards=monthly_login_bonus_rewards,
            )
        )

    login_bonus: list[LoginBonusItem] = []

    for e in soup.css(".bonus_block_on, .bonus_block_off"):
        bonus_days_block = e.css_first(".bonus_days_block")

        if bonus_days_block is None:
            continue

        day = chuni_int(bonus_days_block.text().removeprefix("Day "))
        icon_url = e.css_first(".bonus_reward_block img").attrs["src"]
        name = e.css_first(".bonus_reward_honor_text").text().strip()
        obtained = e.css_first(".bonus_reward_get") is not None

        login_bonus.append(
            LoginBonusItem(
                day=day,
                icon_url=icon_url,
                name=name,
                obtained=obtained,
            )
        )

    daily_bonus: list[DailyBonus] = []

    for e in soup.css(".weekday_bonus_block, .weekday_bonus_today"):
        weekday_name = e.css_first(".weekday_bonus_week").text()
        weekday = WEEKDAY_MAP[weekday_name]
        icon_url = e.css_first(".weekday_bonus_info_icon img").attrs["src"]
        bonus = e.css_first(".weekday_bonus_info_text").text().strip()
        is_today = "weekday_bonus_today" in str(e.attrs["class"])

        daily_bonus.append(
            DailyBonus(
                weekday=weekday,
                icon_url=icon_url,
                bonus=bonus,
                is_today=is_today,
            )
        )

    return LoginBonus(
        received_bonus_today=received_bonus_today,
        monthly_login_bonus=monthly_bonuses,
        login_bonus=login_bonus,
        daily_bonus=daily_bonus,
    )


def parse_leaderboard(soup: LexborHTMLParser) -> Leaderboard:
    updated_at_elem = soup.css_first(".ranking_update")

    if updated_at_elem is None:
        msg = "Could not find leaderboard update date."
        raise ValueError(msg)

    lb = Leaderboard(
        updated_at=parse_time(updated_at_elem.text().removeprefix("Update on：")),  # noqa: RUF001
        ranking=[],
    )

    for entry in soup.css(".rank_block"):
        position_elem = entry.css_first(".rank_block_rank")
        player_name_elem = entry.css_first(".rank_block_name")
        score_elem = entry.css_first(".rank_score_block .rank_block_num")
        ajc_count_elem = entry.css_first(".rank_score_block .rank_block_theory_text")
        last_raised_elem = entry.css_first(".rank_block_date, .rank_block_date_new")

        if (
            position_elem is None
            or player_name_elem is None
            or score_elem is None
            or last_raised_elem is None
        ):
            continue

        lb_entry = LeaderboardEntry(
            position=chuni_int(position_elem.text()),
            player_name=player_name_elem.text(),
            score=chuni_int(score_elem.text()),
            judgements=None,
            clear_lamp=None,
            combo_lamp=None,
            ajc_count=chuni_int(ajc_count_elem.text())
            if ajc_count_elem is not None
            else None,
            achieved_at=parse_time(last_raised_elem.text()),
        )
        lb.ranking.append(lb_entry)

    return lb


def parse_linked_verse_progress(
    soup: LexborHTMLParser,
) -> dict[LinkedGate, LinkedGateStatus]:
    result: dict[LinkedGate, LinkedGateStatus] = {}

    for gate, element in zip(
        LinkedGate,
        soup.css(".linked_verse_icon_status_block .linked_verse_icon_block img"),
        strict=False,
    ):
        src = element.attrs.get("src")

        if not isinstance(src, str):
            continue

        filename = src.split("/")[-1].split(".")[0]

        if filename in LINKED_VERSE_PROGRESS_BADGES:
            result[gate] = LINKED_VERSE_PROGRESS_BADGES[filename][1]
        else:
            _logger.warning("Unknown image URL %s for gate %r", src, gate)
            result[gate] = LinkedGateStatus.not_found

    return result


def parse_linked_gate_leaderboard(soup: LexborHTMLParser) -> LinkedGateLeaderboard:
    title_elem = soup.css_first(".course_musicdata_title_text")
    artist_elem = soup.css_first(".course_musicdata_artist")
    jacket_elem = soup.css_first(".play_jacket_img img")
    clear_date_elem = soup.css_first(".course_playdata_leftside > .text_l > .text_b")
    update_date_elem = soup.css_first(".ranking_update")

    if (
        title_elem is None
        or artist_elem is None
        or jacket_elem is None
        or update_date_elem is None
    ):
        msg = "Linked GATE leaderboard missing required information"
        raise ValueError(msg)

    title = title_elem.text().strip()
    artist = artist_elem.text()
    jacket_url = jacket_elem.attrs["src"]
    clear_date = clear_date_elem.text().strip() if clear_date_elem is not None else None

    if clear_date == "----/--/-- --:--:--":
        clear_date = None

    lb = LinkedGateLeaderboard(
        title=title,
        artist=artist,
        jacket_url=jacket_url,
        cleared_at=parse_time(clear_date) if clear_date is not None else None,
        updated_at=parse_time(
            update_date_elem.text().removeprefix("Update on：")  # noqa: RUF001
        ),
        ranking=[],
    )

    for element in soup.css(".rank_block_s"):
        position_elem = element.css_first(".rank_block_rank_s")
        player_name_elem = element.css_first(".rank_block_name_unlock")
        achieved_at_elem = element.css_first(".rank_block_num_linked")
        link_level_elem = element.css_first(
            ".linked_verse_ranking_clear_course_level_img img"
        )

        if (
            position_elem is None
            or player_name_elem is None
            or achieved_at_elem is None
            or link_level_elem is None
        ):
            continue

        lb.ranking.append(
            LinkedGateLeaderboardEntry(
                position=chuni_int(position_elem.text()),
                player_name=player_name_elem.text(),
                achieved_at=parse_time(achieved_at_elem.text()),
                link_level=LinkLevel(
                    chuni_int(extract_last_part(link_level_elem.attrs["src"]))
                ),
            )
        )

    return lb


def parse_friend_vs(
    soup: LexborHTMLParser,
) -> tuple[list[PersonalBest], list[PersonalBest]]:
    your_pbs: list[PersonalBest] = []
    their_pbs: list[PersonalBest] = []

    for block in soup.css(".music_box"):
        song = Song(id=MISSING, title=block.css_first(".block_underline > div").text())
        chart = Chart(difficulty=difficulty_from_imgurl(block.attrs["class"]))
        info_blocks = block.css(".vs_list_infoblock")

        if len(info_blocks) != 2:
            continue

        your_block, their_block = info_blocks
        your_score = chuni_int(your_block.css_first(".play_musicdata_highscore").text())
        your_lamps = get_rank_and_lamps(your_block.css_first(".vs_list_mybatch"))
        your_pbs.append(
            PersonalBest(
                song=song,
                chart=chart,
                score=your_score,
                clear_lamp=your_lamps[1],
                combo_lamp=your_lamps[2],
                chain_lamp=your_lamps[3],
            )
        )

        their_score = chuni_int(
            their_block.css_first(".play_musicdata_highscore").text()
        )
        their_lamps = get_rank_and_lamps(their_block.css_first(".vs_list_friendbatch"))
        their_pbs.append(
            PersonalBest(
                song=song,
                chart=chart,
                score=their_score,
                clear_lamp=their_lamps[1],
                combo_lamp=their_lamps[2],
                chain_lamp=their_lamps[3],
            )
        )

    return (your_pbs, their_pbs)


def parse_team_ranking(soup: LexborHTMLParser) -> TeamRanking:
    ranking_update_elem = soup.css_first(".ranking_update")

    if ranking_update_elem is None:
        msg = "Missing ranking update date"
        raise ValueError(msg)

    updated_at = parse_time(
        ranking_update_elem.text().removeprefix("Update on：")  # noqa: RUF001
    )
    ranking: list[TeamRankingEntry] = []

    for e in soup.css(".rank_block"):
        position_elem = e.css_first(".rank_block_rank")
        name_elem = e.css_first(".rank_teamname")
        points_elem = e.css_first(".rank_block_team_num")
        delta_elem = e.css_first(".rank_block_team_diff")
        rank_state_elem = e.css_first("img.rank_state_img")

        if (
            position_elem is None
            or name_elem is None
            or points_elem is None
            or delta_elem is None
            or rank_state_elem is None
        ):
            continue

        position = int(position_elem.text())
        team_name = name_elem.text()
        points = chuni_int(points_elem.text())
        delta = chuni_int(
            delta_elem.text()
            .removeprefix("(")
            .removesuffix(")")
            .replace("＋", "")  # noqa: RUF001
            .replace("±", "")
            .replace("－", "-")  # noqa: RUF001
        )
        ranking_delta = getattr(
            RankingDelta, extract_last_part(rank_state_elem.attrs["src"])
        )

        ranking.append(
            TeamRankingEntry(
                position=position,
                team_name=team_name,
                points=points,
                delta=delta,
                ranking_delta=ranking_delta,
            )
        )

    return TeamRanking(updated_at=updated_at, ranking=ranking)


def parse_rating_ranking(soup: LexborHTMLParser) -> RatingRanking:
    ranking_update_elem = soup.css_first(".ranking_update")

    if ranking_update_elem is None:
        msg = "Missing ranking update date"
        raise ValueError(msg)

    updated_at = parse_time(
        ranking_update_elem.text().removeprefix("Update on：")  # noqa: RUF001
    )
    ranking: list[RatingRankingEntry] = []

    for e in soup.css(".rank_block_s"):
        position_elem = e.css_first(".rank_block_rank_s")
        name_elem = e.css_first(".rank_block_name_s")
        rating_elem = e.css_first(".rank_block_rating_num")

        if position_elem is None or name_elem is None or rating_elem is None:
            continue

        position = int(position_elem.text())
        player_name = name_elem.text()
        rating = parse_player_rating(rating_elem.css("img"))

        ranking.append(
            RatingRankingEntry(
                position=position, player_name=player_name, rating=rating
            )
        )

    return RatingRanking(updated_at=updated_at, ranking=ranking)


def parse_score_ranking(soup: LexborHTMLParser) -> ScoreRanking:
    ranking_update_elem = soup.css_first(".ranking_update")

    if ranking_update_elem is None:
        msg = "Missing ranking update date"
        raise ValueError(msg)

    updated_at = parse_time(
        ranking_update_elem.text().removeprefix("Update on：")  # noqa: RUF001
    )
    ranking: list[ScoreRankingEntry] = []

    for e in soup.css(".rank_block_s"):
        position_elem = e.css_first(".rank_block_rank_s")
        name_elem = e.css_first(".rank_block_name_s")
        score_elem = e.css_first(".rank_block_num_s")

        if position_elem is None or name_elem is None or score_elem is None:
            continue

        position = int(position_elem.text())
        player_name = name_elem.text()
        score = chuni_int(score_elem.text())

        ranking.append(
            ScoreRankingEntry(position=position, player_name=player_name, score=score)
        )

    return ScoreRanking(updated_at=updated_at, ranking=ranking)


def parse_currency_ranking(soup: LexborHTMLParser) -> CurrencyRanking:
    ranking_update_elem = soup.css_first(".ranking_update")

    if ranking_update_elem is None:
        msg = "Missing ranking update date"
        raise ValueError(msg)

    updated_at = parse_time(
        ranking_update_elem.text().removeprefix("Update on：")  # noqa: RUF001
    )
    ranking: list[CurrencyRankingEntry] = []

    for e in soup.css(".rank_block_s"):
        position_elem = e.css_first(".rank_block_rank_s")
        name_elem = e.css_first(".rank_block_name_s")
        currency_elem = e.css_first(".rank_block_num_s")

        if position_elem is None or name_elem is None or currency_elem is None:
            continue

        position = int(position_elem.text())
        player_name = name_elem.text()
        currency = chuni_int(currency_elem.text())

        ranking.append(
            CurrencyRankingEntry(
                position=position, player_name=player_name, currency=currency
            )
        )

    return CurrencyRanking(updated_at=updated_at, ranking=ranking)
