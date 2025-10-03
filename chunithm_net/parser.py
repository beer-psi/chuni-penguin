# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false, reportArgumentType=false
import logging
import re
from pathlib import Path
from typing import cast

import msgspec
from bs4 import BeautifulSoup, Tag

from .consts import _KEY_DETAILED_PARAMS, KEY_SONG_ID
from .models.enums import (
    ChainType,
    ClearType,
    ComboType,
    CourseClass,
    Possession,
    Rank,
    SkillClass,
)
from .models.player_data import (
    Currency,
    Overpower,
    PlayerCollections,
    PlayerData,
    Team,
    Title,
    UserAvatar,
)
from .models.record import (
    CourseRecord,
    DetailedParams,
    DetailedRecentRecord,
    Judgements,
    MusicRecord,
    NoteType,
    RecentRecord,
    Record,
    Skill,
)
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
        title_rarity = extract_last_part(title_background_filename)

        if title_rarity == "noSet":
            return None

        title_content_elem = element.select_one(
            ".player_honor_text span, .honor_now_text span"
        )

        if title_content_elem is None:
            msg = "Invalid title (missing title content on normal titles)"
            raise ValueError(msg)

        title_content = title_content_elem.get_text()
    elif special_title := SPECIAL_TITLES.get(title_background_filename):
        title_content = special_title.content
        title_rarity = special_title.rarity
    else:
        _logger.warning(
            "Ignoring unknown special title with URL %s", title_background_url
        )
        return None

    return Title(title_content, title_rarity)


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

    title_elements = soup.select(".player_honor_short")
    titles: list[Title] = [
        title for elem in title_elements if (title := parse_title(elem)) is not None
    ]

    rating = parse_player_rating(soup.select(".player_rating_num_block img"))

    overpower = soup.select_one(".player_overpower_text").get_text().split(" ")
    overpower_value = float(overpower[0])
    overpower_progress = (
        float(overpower[1].replace("(", "").replace(")", "").replace("%", "")) / 100
    )

    last_play_date_str = soup.select_one(".player_lastplaydate_text").get_text()
    last_play_date = parse_time(last_play_date_str)

    reborn_elem = soup.select_one(".player_reborn")
    reborn = chuni_int(reborn_elem.get_text()) if reborn_elem else 0

    possession_elem = soup.select_one(".box_playerprofile")
    possession = (
        Possession.from_str(extract_last_part(possession_elem["style"]))  # type: ignore[reportGeneralTypeIssues]
        if possession_elem and possession_elem.has_attr("style")
        else Possession.NONE
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

    return PlayerData(
        character=character,
        character_frame=(
            f"https://chunithm-net-eng.com/mobile/images/charaframe_{character_frame}.png"
            if character_frame
            else None
        ),
        avatar=avatar,
        name=name,
        lv=lv,
        reborn=reborn,
        possession=possession,
        team=Team(name=team_name) if team_name else None,
        titles=titles,
        rating=rating,
        overpower=Overpower(overpower_value, overpower_progress),
        last_play_date=last_play_date,
        emblem=emblem,
        medal=medal,
    )


def parse_player_data(soup: BeautifulSoup) -> PlayerData:
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
    data.playcount = playcount

    data.friend_code = soup.select_one(
        ".user_data_friend_code .user_data_text span:not(.font_90)"
    ).get_text()

    return data


def parse_basic_recent_record(record: Tag) -> RecentRecord:
    idx_elem = record.select_one("form input[name=idx]")

    assert idx_elem is not None

    idx = int(cast(str, idx_elem["value"]))
    token = cast(str, record.select_one("form input[name=token]")["value"])
    detailed = DetailedParams(idx, token)

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
        rank = Rank.D
        clear_lamp = ClearType.FAILED
        combo_lamp = ComboType.NONE
        chain_lamp = ChainType.NONE

    score = RecentRecord(
        track=track,
        date=date,
        title=title,
        jacket=jacket,
        difficulty=difficulty_from_imgurl(
            cast(str, record.select_one(".play_track_result img")["src"])
        ),
        score=score,
        rank=rank,
        clear_lamp=clear_lamp,
        combo_lamp=combo_lamp,
        chain_lamp=chain_lamp,
        new_record=new_record,
    )
    score.extras[_KEY_DETAILED_PARAMS] = detailed

    return score


def parse_music_record(soup: BeautifulSoup, song_id: int) -> list[MusicRecord]:
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
            rank = Rank.D
            clear_lamp = ClearType.FAILED
            combo_lamp = ComboType.NONE
            chain_lamp = ChainType.NONE

        score = MusicRecord(
            title=title,
            jacket=jacket,
            difficulty=difficulty_from_imgurl(" ".join(block["class"])),
            score=chuni_int(
                elem.get_text()
                if (elem := block.select_one(".musicdata_score_num .text_b"))
                is not None
                else "0"
            ),
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


def parse_music_for_rating(soup: BeautifulSoup) -> list[Record]:
    records = []
    for x in soup.select("form:has(.w388.musiclist_box)"):
        if (score_elem := x.select_one(".play_musicdata_highscore .text_b")) is None:
            continue

        if (musicdata := x.select_one(".play_musicdata_icon")) is not None:
            rank, clear_lamp, combo_lamp, chain_lamp = get_rank_and_lamps(musicdata)
        else:
            rank = Rank.D
            clear_lamp = ClearType.FAILED
            combo_lamp = ComboType.NONE
            chain_lamp = ChainType.NONE

        div = x.select_one(".w388.musiclist_box")
        score = Record(
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


def parse_detailed_recent_record(soup: BeautifulSoup) -> DetailedRecentRecord:
    def get_judgement_count(class_name):
        return chuni_int(soup.select_one(class_name).get_text().replace(",", ""))

    def get_note_percentage(class_name):
        return float(soup.select_one(class_name).get_text().replace("%", "")) / 100

    record = DetailedRecentRecord.from_basic(
        parse_basic_recent_record(cast("Tag", soup.select_one(".frame01_inside")))
    )

    record.max_combo = chuni_int(
        soup.select_one(".play_data_detail_maxcombo_block").get_text()
    )

    jcrit = get_judgement_count(".text_critical.play_data_detail_judge_text")
    justice = get_judgement_count(".text_justice.play_data_detail_judge_text")
    attack = get_judgement_count(".text_attack.play_data_detail_judge_text")
    miss = get_judgement_count(".text_miss.play_data_detail_judge_text")
    record.judgements = Judgements(jcrit, justice, attack, miss)

    tap = get_note_percentage(".text_tap_red.play_data_detail_notes_text")
    hold = get_note_percentage(".text_hold_yellow.play_data_detail_notes_text")
    slide = get_note_percentage(".text_slide_blue.play_data_detail_notes_text")
    air = get_note_percentage(".text_air_green.play_data_detail_notes_text")
    flick = get_note_percentage(".text_flick_skyblue.play_data_detail_notes_text")
    record.note_type = NoteType(tap, hold, slide, air, flick)

    record.character = soup.select_one(".play_data_chara_name").get_text()

    skill_name = soup.select_one(".play_data_skill_name").get_text()
    record.skill = Skill(skill_name, None)

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
            rank = Rank.D
            clear_lamp = ClearType.FAILED
            combo_lamp = ComboType.NONE

        cls = extract_last_part(" ".join(x.select_one(".w388.musiclist_box")["class"]))

        if cls == "class10":
            course_cls = CourseClass.I
        elif cls == "class11":
            course_cls = CourseClass.II
        elif cls == "class12":
            course_cls = CourseClass.III
        elif cls == "class13":
            course_cls = CourseClass.IV
        elif cls == "class14":
            course_cls = CourseClass.V
        elif cls == "class20":
            course_cls = CourseClass.INFINITE
        elif cls == "class22":
            course_cls = CourseClass.EXTRA
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
