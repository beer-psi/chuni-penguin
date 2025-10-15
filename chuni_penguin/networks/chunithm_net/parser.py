# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false, reportArgumentType=false
import calendar
import logging
import re
from pathlib import Path
from typing import cast

import msgspec
from bs4 import BeautifulSoup, Tag

from chuni_penguin.networks.consts import KEY_SONG_ID
from chuni_penguin.networks.types import (
    ChainLamp,
    ClearLamp,
    ComboLamp,
    CourseClass,
    CourseRecord,
    Currency,
    DailyBonus,
    Judgements,
    Leaderboard,
    LeaderboardEntry,
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
    Rarity,
    RatingSystem,
    RecentScore,
    Skill,
    SkillClass,
    Team,
    TeamEmblem,
    Title,
    UserAvatar,
)

from .consts import _KEY_DETAILED_PARAMS_IDX
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


def parse_avatar(avatar_group: Tag) -> UserAvatar:
    return UserAvatar(
        base="https://new.chunithm-net.com/chuni-mobile/html/mobile/images/avatar_base.png",
        back=avatar_group.select_one(".avatar_back img")["src"],
        skinfoot_r=avatar_group.select_one(".avatar_skinfoot_r img")["src"],
        skinfoot_l=avatar_group.select_one(".avatar_skinfoot_l img")["src"],
        skin=avatar_group.select_one(".avatar_skin img")["src"],
        wear=avatar_group.select_one(".avatar_wear img")["src"],
        face=avatar_group.select_one(".avatar_face img")["src"],
        face_cover=avatar_group.select_one(".avatar_faceCover img")["src"],
        head=avatar_group.select_one(".avatar_head img")["src"],
        hand_r=avatar_group.select_one(".avatar_hand_r img")["src"],
        hand_l=avatar_group.select_one(".avatar_hand_l img")["src"],
        item_r=avatar_group.select_one(".avatar_item_r img")["src"],
        item_l=avatar_group.select_one(".avatar_item_l img")["src"],
        front=avatar_group.select_one(".avatar_front img")["src"],
    )


def parse_title(element: Tag) -> Title | None:
    title_style = element.get("style")

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

        title_content_elem = element.select_one(
            ".player_honor_text span, .honor_now_text span"
        )

        if title_content_elem is None:
            msg = "Invalid title (missing title content on normal titles)"
            raise ValueError(msg)

        title_content = title_content_elem.get_text()
        title_rarity = Rarity(title_rarity)
    elif special_title := SPECIAL_TITLES.get(title_background_filename):
        title_content = special_title.content
        title_rarity = Rarity(special_title.rarity)
    else:
        _logger.warning(
            "Ignoring unknown special title with URL %s", title_background_url
        )
        return None

    return Title(content=title_content, rarity=title_rarity)


def parse_player_card_and_avatar(soup: BeautifulSoup):
    if (e := soup.select_one(".player_chara")) is not None:
        img = e.select_one("img")
        character = img.attrs["src"] if e else None

        character_frame = (
            extract_last_part(e.attrs["style"]) if "style" in e.attrs else None
        )
    else:
        character = None
        character_frame = None

    name = soup.select_one(".player_name_in").get_text()
    lv = chuni_int(soup.select_one(".player_lv").get_text())

    team_name_elem = soup.select_one(".player_team_name")
    team_name = team_name_elem.get_text() if team_name_elem else None

    team_emblem_elem = soup.select_one(
        ".player_team_emblem_normal, .player_team_emblem_silver, .player_team_emblem_gold, .player_team_emblem_rainbow"
    )
    team_emblem = (
        TeamEmblem(extract_last_part(team_emblem_elem["class"][0]))
        if team_emblem_elem
        else None
    )

    if team_name and team_emblem:
        team = Team(name=team_name, emblem=team_emblem)
    else:
        team = None

    title_elements = soup.select(".player_honor_short")
    titles: list[Title] = [
        title for elem in title_elements if (title := parse_title(elem)) is not None
    ]

    rating = parse_player_rating(soup.select(".player_rating_num_block img"))

    overpower = soup.select_one(".player_overpower_text").get_text().split(" ")
    overpower_value = float(overpower[0])
    overpower_progress = float(
        overpower[1].replace("(", "").replace(")", "").replace("%", "")
    )

    last_play_date_str = soup.select_one(".player_lastplaydate_text").get_text()
    last_play_date = parse_time(last_play_date_str)

    reborn_elem = soup.select_one(".player_reborn")
    reborn = chuni_int(reborn_elem.get_text()) if reborn_elem else 0

    possession_elem = soup.select_one(".box_playerprofile")
    possession = (
        Possession(extract_last_part(possession_elem["style"]))  # type: ignore[reportGeneralTypeIssues]
        if possession_elem and possession_elem.has_attr("style")
        else Possession.none
    )

    classemblem_base_elem = soup.select_one(".player_classemblem_base img")
    emblem = (
        SkillClass(
            chuni_int(extract_last_part(classemblem_base_elem["src"]))  # type: ignore[reportGeneralTypeIssues]
        )
        if classemblem_base_elem and classemblem_base_elem.has_attr("src")
        else None
    )

    classemblem_top_elem = soup.select_one(".player_classemblem_top img")
    medal = (
        SkillClass(
            chuni_int(extract_last_part(classemblem_top_elem["src"]))  # type: ignore[reportGeneralTypeIssues]
        )
        if classemblem_top_elem and classemblem_top_elem.has_attr("src")
        else None
    )

    avatar_group = soup.select_one(".avatar_group")
    avatar = parse_avatar(avatar_group)

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
        rating_systems=[RatingSystem(name="Rating", value=rating)],
        over_power=OverPower(value=overpower_value, percentage=overpower_progress),
        possession=possession,
        last_played=last_play_date,
        user_avatar=avatar,
    )


def parse_player_data(soup: BeautifulSoup) -> Profile:
    data = parse_player_card_and_avatar(soup)

    owned_currency = chuni_int(
        soup.select_one(".user_data_point .user_data_text").get_text()
    )
    total_currency = chuni_int(
        soup.select_one(".user_data_total_point .user_data_text").get_text()
    )
    data.currency = Currency(owned_currency, total_currency)

    playcount = chuni_int(
        soup.select_one(".user_data_play_count .user_data_text").get_text()
    )
    data.total_credits = playcount

    data.friend_code = soup.select_one(
        ".user_data_friend_code .user_data_text span:not(.font_90)"
    ).get_text()

    return data


def parse_basic_recent_record(record: Tag) -> RecentScore:
    idx_elem = record.select_one("form input[name=idx]")

    assert idx_elem is not None

    idx = int(cast(str, idx_elem["value"]))

    date = parse_time(
        (record.select_one(".play_datalist_date, .box_inner01")).get_text()
    )
    jacket_elem = record.select_one(".play_jacket_img img")
    if (jacket := cast(str | None, jacket_elem.get("data-original"))) is None:
        jacket = cast(str, jacket_elem["src"])
    track = int(record.select_one(".play_track_text").get_text().split(" ")[1])
    title = record.select_one(".play_musicdata_title").get_text()

    score = int(
        record.select_one(".play_musicdata_score_text").get_text().replace(",", "")
    )
    new_record = record.select_one(".play_musicdata_score_img") is not None

    if (rank_elem := record.select_one(".play_musicdata_icon")) is not None:
        rank, clear_lamp, combo_lamp, chain_lamp = get_rank_and_lamps(rank_elem)
    else:
        rank = Rank.d
        clear_lamp = ClearLamp.failed
        combo_lamp = ComboLamp.none
        chain_lamp = ChainLamp.none

    score = RecentScore(
        title=title,
        difficulty=difficulty_from_imgurl(
            cast(str, record.select_one(".play_track_result img")["src"])
        ),
        score=score,
        jacket_url=jacket,
        rank=rank,
        clear_lamp=clear_lamp,
        combo_lamp=combo_lamp,
        chain_lamp=chain_lamp,
        achieved_at=date,
        track_no=track,
        is_new_record=new_record,
    )
    score.extras[_KEY_DETAILED_PARAMS_IDX] = idx

    return score


def parse_music_record(soup: BeautifulSoup, song_id: int) -> list[PersonalBest]:
    jacket = (
        str(elem["src"]) if (elem := soup.select_one(".play_jacket_img img")) else ""
    )
    title = (
        elem.get_text(strip=True)
        if (
            elem := soup.select_one(
                ".play_musicdata_title, .play_musicdata_worldsend_title"
            )
        )
        else ""
    )
    records = []
    for block in soup.select(".music_box"):
        if (musicdata := block.select_one(".play_musicdata_icon")) is not None:
            rank, clear_lamp, combo_lamp, chain_lamp = get_rank_and_lamps(musicdata)
        else:
            rank = Rank.d
            clear_lamp = ClearLamp.failed
            combo_lamp = ComboLamp.none
            chain_lamp = ChainLamp.none

        score = PersonalBest(
            title=title,
            difficulty=difficulty_from_imgurl(" ".join(block["class"])),
            score=chuni_int(
                elem.get_text()
                if (elem := block.select_one(".musicdata_score_num .text_b"))
                is not None
                else "0"
            ),
            jacket_url=jacket,
            rank=rank,
            clear_lamp=clear_lamp,
            combo_lamp=combo_lamp,
            chain_lamp=chain_lamp,
            play_count=chuni_int(
                elem.get_text().replace("times", "")
                if (
                    elem := block.select_one(
                        ".musicdata_score_num .text_b:-soup-contains(times), .music_box .block_icon_text span:not([class])"
                    )
                )
                is not None
                else "0"
            ),
            ajc_count=chuni_int(elem.get_text())
            if (elem := block.select_one(".musicdata_score_theory_num")) is not None
            else None,
        )
        score.extras[KEY_SONG_ID] = song_id

        records.append(score)

    return records


def parse_music_for_rating(soup: BeautifulSoup) -> list[PersonalBest]:
    records = []
    for x in soup.select("form:has(.w388.musiclist_box)"):
        if (score_elem := x.select_one(".play_musicdata_highscore .text_b")) is None:
            continue

        if (musicdata := x.select_one(".play_musicdata_icon")) is not None:
            rank, clear_lamp, combo_lamp, chain_lamp = get_rank_and_lamps(musicdata)
        else:
            rank = Rank.d
            clear_lamp = ClearLamp.failed
            combo_lamp = ComboLamp.none
            chain_lamp = ChainLamp.none

        div = x.select_one(".w388.musiclist_box")
        score = PersonalBest(
            title=x.select_one(".music_title, .musiclist_worldsend_title").get_text(),
            difficulty=difficulty_from_imgurl(" ".join(div["class"])),
            score=chuni_int(score_elem.get_text()),
            rank=rank,
            clear_lamp=clear_lamp,
            combo_lamp=combo_lamp,
            chain_lamp=chain_lamp,
        )
        score.extras[KEY_SONG_ID] = int(
            str(x.select_one("form input[name=idx]")["value"])
        )

        records.append(score)
    return records


def parse_detailed_recent_record(soup: BeautifulSoup) -> RecentScore:
    def get_judgement_count(class_name):
        return chuni_int(soup.select_one(class_name).get_text().replace(",", ""))

    def get_note_percentage(class_name):
        return float(soup.select_one(class_name).get_text().replace("%", ""))

    record = parse_basic_recent_record(soup.select_one(".frame01_inside"))

    record.max_combo = chuni_int(
        soup.select_one(".play_data_detail_maxcombo_block").get_text()
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

    record.character = soup.select_one(".play_data_chara_name").get_text()

    skill_name = soup.select_one(".play_data_skill_name").get_text()
    record.skill = Skill(name=skill_name, grade=None)

    if skill_grade := soup.select_one(".play_data_skill_grade"):
        record.skill.grade = chuni_int(skill_grade.text)

    record.skill_result = chuni_int(
        soup.select_one(".play_musicdata_skilleffect_text").get_text().replace("+", "")
    )
    record.extras[KEY_SONG_ID] = int(
        str(soup.select_one("form input[name=idx]")["value"])
    )
    return record


def parse_course_list(soup: BeautifulSoup):
    courses: list[CourseRecord] = []

    for x in soup.select("form:has(.w388.musiclist_box)"):
        if (score_elem := x.select_one(".play_musicdata_highscore .text_b")) is None:
            continue

        if (musicdata_icon := x.select_one(".play_musicdata_icon")) is not None:
            rank, clear_lamp, combo_lamp = get_course_rank_and_lamps(musicdata_icon)
        else:
            rank = Rank.d
            clear_lamp = ClearLamp.failed
            combo_lamp = ComboLamp.none

        cls = extract_last_part(" ".join(x.select_one(".w388.musiclist_box")["class"]))

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
            id=int(str(x.select_one("form input[name=idx]")["value"])),
            cls=course_cls,
            name=x.select_one(".music_title").get_text(),
            score=chuni_int(score_elem.get_text()),
            rank=rank,
            clear_lamp=clear_lamp,
            combo_lamp=combo_lamp,
        )

        courses.append(course)

    return courses


def parse_collection_customize(soup: BeautifulSoup) -> PlayerCollections:
    titles: list[Title] = [
        title
        for elem in soup.select(".honor_now")
        if (title := parse_title(elem)) is not None
    ]

    return PlayerCollections(
        avatar=parse_avatar(soup.select_one(".avatar_customise_group")),
        titles=titles,
        nameplate=soup.select_one(".nameplate_now img")["src"],
        map_icon=soup.select_one(".mapicon_now img")["src"],
        system_voice=soup.select_one(".systemvoice_now img")["src"],
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


def parse_login_bonus(soup: BeautifulSoup) -> LoginBonus:
    login_bonus_status = soup.select_one(
        r':-soup-contains("Today\'s Login Bonus")'
    ).get_text()
    received_bonus_today = "Not achieved" not in login_bonus_status

    monthly_login_bonus_name = soup.select(".box01_title")[0].get_text().strip()

    monthly_days_logged_in: int = 0

    for e in soup.select(".monthly_cumulative_login_bonus_days_count_num img"):
        digit = extract_last_part(e["src"])
        monthly_days_logged_in = monthly_days_logged_in * 10 + int(digit)

    monthly_login_bonus_rewards: list[LoginBonusItem] = []

    for e in soup.select(".monthly_cumulative_login_bonus_reward"):
        day = chuni_int(
            e.select_one(".bonus_days_block").get_text().removeprefix("Day ")
        )
        icon_url = e.select_one(".monthly_cumulative_login_bonus_reward_img img")["src"]
        name = e.select_one(".bonus_reward_honor_text").get_text().strip()
        obtained = e.select_one(".bonus_reward_get") is not None

        monthly_login_bonus_rewards.append(
            LoginBonusItem(
                day=day,
                icon_url=icon_url,
                name=name,
                obtained=obtained,
            )
        )

    login_bonus: list[LoginBonusItem] = []

    for e in soup.select(".bonus_block_on, .bonus_block_off"):
        day = chuni_int(
            e.select_one(".bonus_days_block").get_text().removeprefix("Day ")
        )
        icon_url = e.select_one(".bonus_reward_block img")["src"]
        name = e.select_one(".bonus_reward_honor_text").get_text().strip()
        obtained = e.select_one(".bonus_reward_get") is not None

        login_bonus.append(
            LoginBonusItem(
                day=day,
                icon_url=icon_url,
                name=name,
                obtained=obtained,
            )
        )

    daily_bonus: list[DailyBonus] = []

    for e in soup.select(".weekday_bonus_block, .weekday_bonus_today"):
        weekday_name = e.select_one(".weekday_bonus_week").get_text()
        weekday = WEEKDAY_MAP[weekday_name]
        icon_url = e.select_one(".weekday_bonus_info_icon img")["src"]
        bonus = e.select_one(".weekday_bonus_info_text").get_text().strip()
        is_today = "weekday_bonus_today" in e["class"]

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
        monthly_login_bonus=MonthlyLoginBonus(
            name=monthly_login_bonus_name,
            days_logged_in=monthly_days_logged_in,
            rewards=monthly_login_bonus_rewards,
        ),
        login_bonus=login_bonus,
        daily_bonus=daily_bonus,
    )


def parse_leaderboard(soup: BeautifulSoup) -> Leaderboard:
    updated_at_elem = soup.select_one(".ranking_update")

    if updated_at_elem is None:
        msg = "Could not find leaderboard update date."
        raise ValueError(msg)

    lb = Leaderboard(
        updated_at=parse_time(updated_at_elem.text.removeprefix("Update on：")),  # noqa: RUF001
        ranking=[],
    )

    for entry in soup.select(".rank_block"):
        position_elem = entry.select_one(".rank_block_rank")
        player_name_elem = entry.select_one(".rank_block_name")
        score_elem = entry.select_one(".rank_score_block .rank_block_num")
        ajc_count_elem = entry.select_one(".rank_score_block .rank_block_theory_text")
        last_raised_elem = entry.select_one(".rank_block_date, .rank_block_date_new")

        if (
            position_elem is None
            or player_name_elem is None
            or score_elem is None
            or last_raised_elem is None
        ):
            continue

        lb_entry = LeaderboardEntry(
            position=chuni_int(position_elem.text),
            player_name=player_name_elem.text,
            score=chuni_int(score_elem.text),
            judgements=None,
            ajc_count=chuni_int(ajc_count_elem.text)
            if ajc_count_elem is not None
            else None,
            achieved_at=parse_time(last_raised_elem.text),
        )
        lb.ranking.append(lb_entry)

    return lb
