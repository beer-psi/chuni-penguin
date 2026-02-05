import concurrent.futures
import csv
import itertools
import subprocess
import traceback
from pathlib import Path
from typing import Optional, overload
from xml.etree import ElementTree

import httpx
import httpx_aiohttp
from PIL import Image
from sqlalchemy import delete, func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.stdlib import BoundLogger

from chuni_penguin.constants import ASSETS_DIR
from chuni_penguin.database import (
    Chart,
    Course,
    CourseTrack,
    Song,
    course_track_charts,
)
from chuni_penguin.networks.types import CourseClass, Difficulty

VERSIONS = [
    "CHUNITHM",
    "CHUNITHM PLUS",
    "AIR",
    "AIR PLUS",
    "STAR",
    "STAR PLUS",
    "AMAZON",
    "AMAZON PLUS",
    "CRYSTAL",
    "CRYSTAL PLUS",
    "PARADISE",
    "PARADISE LOST",
    "NEW",
    "NEW PLUS",
    "SUN",
    "SUN PLUS",
    "LUMINOUS",
    "LUMINOUS PLUS",
    "VERSE",
    "X-VERSE",
    "X-VERSE-X",
]
WE_LEVEL_OVERRIDES = {
    8244: "分☆☆☆ (LASTMORN)",
    8245: "分☆☆☆ (Implexrough)",
    8246: "分☆☆☆ (Shannon's Theorem)",
    8247: "分☆☆☆ (Just Say It)",
    8248: "分☆☆☆ (2anyFirst)",
    8249: "分☆☆☆ (Alt Futur)",
}
B30_JACKET_WIDTH = 110
B30_JACKET_HEIGHT = 110
B30_BASE_IMAGES = {
    Difficulty.basic: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_0.webp"),
    Difficulty.advanced: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_1.webp"),
    Difficulty.expert: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_2.webp"),
    Difficulty.master: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_3.webp"),
    Difficulty.ultima: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_4.webp"),
}
COURSE_CLASS_MAP = {
    10: CourseClass.i,
    11: CourseClass.ii,
    12: CourseClass.iii,
    13: CourseClass.iv,
    14: CourseClass.v,
    20: CourseClass.infinite,
    22: CourseClass.extra,
}


@overload
def gettext(p: ElementTree.Element, path: str) -> Optional[str]: ...


@overload
def gettext(p: ElementTree.Element, path: str, default: str) -> str: ...


def gettext(
    p: ElementTree.Element, path: str, default: Optional[str] = None
) -> Optional[str]:
    if (e := p.find(path)) is not None:
        return e.text
    return default


def extract_jacket(
    song_id: int, jacket_file: Path, alt_suffix: str = "", *, rotate_180: bool = False
):
    try:
        with Image.open(jacket_file) as im:
            im = im.convert("RGB")

            # Keep the PNG version around to prevent dead links, I'm pretty sure some
            # other tools use these jackets
            im.save(
                ASSETS_DIR / "jackets" / f"{song_id}{alt_suffix}.png",
                format="PNG",
                optimize=True,
            )
            im.save(
                ASSETS_DIR / "jackets" / f"{song_id}{alt_suffix}.webp",
                format="WEBP",
                lossless=True,
            )

            # world's ends arent going to show up in b50 anytime soon
            if song_id >= 8000:
                return

            im_small = im.resize(
                (B30_JACKET_WIDTH, B30_JACKET_HEIGHT), Image.Resampling.LANCZOS
            )

            if rotate_180:
                im_small = im_small.transpose(Image.Transpose.ROTATE_180)

            # pregenerate jacket art merged with b50 base
            for difficulty in Difficulty:
                if difficulty == Difficulty.worlds_end:
                    continue

                with B30_BASE_IMAGES[difficulty]() as b30_base_image:
                    b30_base_image.paste(im_small, (10, 60))
                    b30_base_image.save(
                        ASSETS_DIR
                        / "jackets"
                        / f"{song_id}{alt_suffix}_{difficulty.value}.webp",
                        format="WEBP",
                        lossless=True,
                    )

    except Exception:
        traceback.print_exc()
        raise


def extract_audio(song_id: int, cue_file: Path):
    output_file = cue_file.with_suffix(cue_file.suffix + ".wav")
    subprocess.check_output(["vgmstream-cli", str(cue_file)])

    if not output_file.exists():
        msg = "Conversion from AWB to WAV failed: could not find output file"
        raise Exception(msg)  # noqa: TRY002

    subprocess.check_output(
        [
            "ffmpeg",
            "-i",
            str(output_file),
            "-c:a",
            "libopus",
            "-b:a",
            "96000",
            "-y",
            str(ASSETS_DIR / "audio" / f"{song_id}.ogg"),
        ],
        stderr=subprocess.DEVNULL,
    )
    output_file.unlink()


async def merge_options(
    logger: BoundLogger,
    async_session: async_sessionmaker[AsyncSession],
    data_dir: Path,
    option_dir: Optional[Path],
    *,
    extract_jackets: bool,
    extract_audios: bool,
):
    async with httpx.AsyncClient(
        transport=httpx_aiohttp.AIOHTTPTransport(retries=5)
    ) as client:
        songlist = (
            await client.get("https://chunithm.sega.jp/storage/json/music.json")
        ).json()
        jacket_by_id = {int(x["id"]): x["image"] for x in songlist}

    if extract_jackets:
        (ASSETS_DIR / "jackets").mkdir(exist_ok=True, parents=True)

    if extract_audios:
        (ASSETS_DIR / "audio").mkdir(exist_ok=True, parents=True)

    music_xml_paths = data_dir.glob("**/music/**/Music.xml")
    cue_file_paths = data_dir.glob("**/cueFile/**/CueFile.xml")
    course_rule_paths = data_dir.glob("**/courseRule/**/CourseRule.xml")
    course_paths = data_dir.glob("**/course/**/Course.xml")

    if option_dir is not None:
        music_xml_paths = itertools.chain(
            music_xml_paths,
            option_dir.glob("**/music/**/Music.xml"),
        )
        cue_file_paths = itertools.chain(
            cue_file_paths, option_dir.glob("**/cueFile/**/CueFile.xml")
        )
        course_rule_paths = itertools.chain(
            course_rule_paths, option_dir.glob("**/courseRule/**/CourseRule.xml")
        )
        course_paths = itertools.chain(
            course_paths, option_dir.glob("**/course/**/Course.xml")
        )

    inserted_songs = []
    inserted_charts = []

    with concurrent.futures.ProcessPoolExecutor() as pool:
        for xml_path in music_xml_paths:
            tree = ElementTree.parse(xml_path)
            root = tree.getroot()

            if root.tag != "MusicData":
                logger.warning("%s: Invalid XML (missing MusicData root)", xml_path)
                continue

            song_id = gettext(root, "./name/id")
            catcode = gettext(root, "./genreNames/list/StringID/id")
            genre = gettext(root, "./genreNames/list/StringID/str")
            we_tag_name = gettext(root, "./worldsEndTagName/str")
            release_tag_id = gettext(root, path="./releaseTagName/id")

            if (
                song_id is None
                or catcode is None
                or genre is None
                or we_tag_name is None
                or release_tag_id is None
            ):
                logger.warning("%s: Invalid XML (missing required tags)", xml_path)
                continue

            logger.debug("Reading music ID %s", song_id)
            song_id_int = int(song_id)

            if extract_jackets:
                jacket_file = gettext(root, "./jaketFile/path")

                if not jacket_file:
                    continue

                pool.submit(
                    extract_jacket,
                    song_id_int,
                    xml_path.parent / jacket_file,
                )

                if song_id_int == 2698:
                    cytus2_alt = xml_path.parent / "CHU_UI_Jacket_2698_CytusII.dds"
                    vividstasis_alt = (
                        xml_path.parent / "CHU_UI_Jacket_2698_vividstasis.dds"
                    )
                    musedash_alt = xml_path.parent / "CHU_UI_Jacket_2698_MuseDash.dds"
                    musicdiver_alt = (
                        xml_path.parent / "CHU_UI_Jacket_2698_MusicDiver.dds"
                    )
                    sdvx_alt = xml_path.parent / "CHU_UI_Jacket_2698_SDVX.dds"

                    if cytus2_alt.exists():
                        pool.submit(extract_jacket, song_id_int, cytus2_alt, "_cytus2")

                    if vividstasis_alt.exists():
                        pool.submit(
                            extract_jacket, song_id_int, vividstasis_alt, "_vividstasis"
                        )

                    if musedash_alt.exists():
                        pool.submit(
                            extract_jacket, song_id_int, musedash_alt, "_musedash"
                        )

                    if musicdiver_alt.exists():
                        pool.submit(
                            extract_jacket, song_id_int, musicdiver_alt, "_musicdiver"
                        )

                    if sdvx_alt.exists():
                        pool.submit(extract_jacket, song_id_int, sdvx_alt, "_sdvx")

                elif song_id_int == 45:
                    pool.submit(
                        extract_jacket,
                        song_id_int,
                        xml_path.parent / jacket_file,
                        "_67",
                        rotate_180=True,
                    )

            if we_tag_name != "Invalid":
                genre = "WORLD'S END"

            release_date = gettext(root, "./releaseDate")

            inserted_song = {
                "id": song_id_int,
                "title": gettext(root, "./name/str"),
                "chunithm_catcode": int(catcode),
                "genre": genre,
                "artist": gettext(root, "./artistName/str"),
                "release": f"{release_date[:4]}-{release_date[4:6]}-{release_date[6:]}"
                if release_date
                else None,
                "version": VERSIONS[int(release_tag_id)],
                "bpm": None,
                "min_bpm": None,
                "max_bpm": None,
                "jacket": jacket_by_id.get(song_id_int),
                "available": gettext(root, "./disableFlag") != "true",
                "removed": False,
            }

            for idx, chart in enumerate(
                root.findall("./fumens/MusicFumenData[enable='true']")
            ):
                difficulty = gettext(chart, "./type/data")
                chart_filename = gettext(chart, "./file/path")
                level_str = gettext(chart, "./level")
                level_decimal_str = gettext(chart, "./levelDecimal")

                if (
                    difficulty is None
                    or chart_filename is None
                    or level_str is None
                    or level_decimal_str is None
                ):
                    logger.warning(
                        "%s: Invalid MusicFumenData at index %d (missing required tags)",
                        xml_path,
                        idx,
                    )
                    continue

                logger.debug("Reading music ID %s, difficulty %s", song_id, difficulty)

                level_decimal = int(level_decimal_str)

                if genre == "WORLD'S END":
                    if song_id_int in WE_LEVEL_OVERRIDES:
                        displayed_level = WE_LEVEL_OVERRIDES[song_id_int]
                    else:
                        star_dif_type = int(gettext(root, "./starDifType", "0"))
                        displayed_level = we_tag_name

                        for _ in range(-1, star_dif_type, 2):
                            displayed_level += "☆"

                    const = None
                else:
                    displayed_level = level_str + ("+" if level_decimal >= 50 else "")
                    const = float(f"{level_str}.{level_decimal_str}")

                inserted_chart = {
                    "song_id": song_id_int,
                    "difficulty": "WE"
                    if difficulty == "WORLD'S END"
                    else difficulty[:3],
                    "level": displayed_level,
                    "const": const,
                    "available": inserted_song["available"],
                }

                with xml_path.with_name(chart_filename).open(encoding="utf-8") as f:
                    rd = csv.reader(f, delimiter="\t")

                    for row in rd:
                        if len(row) == 0:
                            continue

                        command = row[0]

                        if command == "BPM_DEF" and inserted_song.get("bpm") is None:
                            inserted_song["bpm"] = float(row[2])
                        if command == "BPM":
                            bpm = float(row[3])

                            if (
                                min_bpm := inserted_song.get("min_bpm")
                            ) is None or bpm < min_bpm:
                                inserted_song["min_bpm"] = bpm
                            if (
                                max_bpm := inserted_song.get("max_bpm")
                            ) is None or bpm > max_bpm:
                                inserted_song["max_bpm"] = bpm
                        elif command == "T_JUDGE_ALL":
                            inserted_chart["maxcombo"] = int(row[1])
                        elif command == "T_JUDGE_TAP":
                            inserted_chart["tap"] = int(row[1])
                        elif command == "T_JUDGE_HLD":
                            inserted_chart["hold"] = int(row[1])
                        elif command == "T_JUDGE_SLD":
                            inserted_chart["slide"] = int(row[1])
                        elif command == "T_JUDGE_AIR":
                            inserted_chart["air"] = int(row[1])
                        elif command == "T_JUDGE_FLK":
                            inserted_chart["flick"] = int(row[1])
                        elif command == "CREATOR":
                            inserted_chart["charter"] = row[1]

                inserted_charts.append(inserted_chart)

            inserted_songs.append(inserted_song)

        if extract_audios:
            for cue_file_path in cue_file_paths:
                tree = ElementTree.parse(cue_file_path)
                root = tree.getroot()

                if root.tag != "CueFileData":
                    logger.warning(
                        "%s: Invalid XML (missing CueFileData root)", cue_file_path
                    )
                    continue

                cue_file_id = gettext(root, "./name/id")
                awb_file = gettext(root, "./awbFile/path")

                if cue_file_id is None or awb_file is None:
                    logger.warning(
                        "%s: Invalid XML (missing ID or awbFile path)", cue_file_path
                    )
                    continue

                if (
                    int(cue_file_id) >= 10000
                ):  # those are actually "FULL COMBO" sounds of different system voices
                    continue

                pool.submit(
                    extract_audio, int(cue_file_id), cue_file_path.parent / awb_file
                )

        pool.shutdown(wait=True)

    inserted_courses = []
    inserted_course_tracks = []
    inserted_course_track_charts = []
    course_rules = {}

    for course_rule_path in course_rule_paths:
        tree = ElementTree.parse(course_rule_path)
        root = tree.getroot()

        if root.tag != "CourseRuleData":
            logger.warning(
                "%s: Invalid XML (missing CourseRuleData root)", course_rule_path
            )
            continue

        course_rule_id = gettext(root, "./name/id")
        life = gettext(root, "./life")
        recovery_life = gettext(root, "./recovery_life")
        clear_life = gettext(root, "./clear_life")
        damage_miss = gettext(root, "./damage_miss")
        damage_attack = gettext(root, "./damage_attack")
        damage_justice = gettext(root, "./damage_justice")
        damage_jcrit = gettext(root, "./damage_justice_c")

        if (
            course_rule_id is None
            or life is None
            or recovery_life is None
            or clear_life is None
            or damage_miss is None
            or damage_attack is None
            or damage_justice is None
            or damage_jcrit is None
        ):
            logger.warning("%s: Invalid XML (missing required tags)", course_rule_path)
            continue

        logger.debug("Reading course rule %s", course_rule_id)

        course_rules[int(course_rule_id)] = {
            "life": int(life),
            "recovery_life": int(recovery_life),
            "clear_life": int(clear_life),
            "damage_miss": int(damage_miss),
            "damage_attack": int(damage_attack),
            "damage_justice": int(damage_justice),
            "damage_jcrit": int(damage_jcrit),
        }

    for course_path in course_paths:
        tree = ElementTree.parse(course_path)
        root = tree.getroot()

        if root.tag != "CourseData":
            logger.warning("%s: Invalid XML (missing CourseData root)", course_path)
            continue

        release_tag_id = gettext(root, path="./releaseTagName/id")
        course_id = gettext(root, "./name/id")
        name = gettext(root, "./name/str")
        cls_id = gettext(root, "./difficulty/id")
        rule_id = gettext(root, "./rule/id")
        is_music_duplicate_allowed = gettext(root, "./isMusicDuplicateAllowed")
        team_only = gettext(root, "./teamOnly")

        if team_only == "true":
            logger.debug("Skipping team-only course %s", course_path)
            continue

        if (
            course_id is None
            or name is None
            or cls_id is None
            or rule_id is None
            or release_tag_id is None
        ):
            logger.warning("%s: Invalid XML (missing required tags)", course_path)
            continue

        course_id = int(course_id)

        if course_id >= 300000:
            logger.debug('Skipping unlock challenge "course" %s', course_path)
            continue

        try:
            cls = COURSE_CLASS_MAP[int(cls_id)]
        except KeyError:
            logger.warning(
                "%s: Course references unknown course class %s", course_path, cls_id
            )
            continue

        try:
            rule = course_rules[int(rule_id)]
        except KeyError:
            logger.warning(
                "%s: Course references unknown course rule %s", course_path, rule_id
            )
            continue

        try:
            version = VERSIONS[int(release_tag_id)]
        except KeyError:
            logger.warning(
                "%s: Course references unknown version %s", course_path, release_tag_id
            )
            continue

        logger.debug("Reading course %s", course_id)

        inserted_courses.append(
            {
                "id": course_id,
                "cls": cls,
                "name": name,
                "version": version,
                "is_duplicate_track_allowed": is_music_duplicate_allowed == "true",
                **rule,
            }
        )

        for i, info in enumerate(root.findall("./infos/CourseMusicDataInfo")):
            ty = gettext(info, "./type")

            if ty is None:
                logger.warning(
                    "CourseMusicDataInfo %s of course %s does not explicitly specify a type, assuming 0",
                    i,
                    course_path,
                )
                ty = "0"

            ty = int(ty)

            if ty == 0:
                song_id = gettext(info, "./selectMusic/musicName/id")
                difficulty = gettext(info, "./selectMusic/musicDiff/data")

                if song_id is None or song_id == "-1" or not difficulty:
                    msg = f"CourseMusicDataInfo of type {ty} (from {course_path}) does not have a selectMusic set"
                    raise ValueError(msg)

                inserted_course_tracks.append(
                    {"course_id": course_id, "track": i + 1, "level": None}
                )
                inserted_course_track_charts.append(
                    {
                        "course_id": course_id,
                        "track": i + 1,
                        "song_id": int(song_id),
                        "difficulty": "WE"
                        if difficulty == "WORLD'S END"
                        else difficulty[:3],
                    }
                )
            elif ty == 1:
                level = gettext(info, "./selectLevel/fromLevel/data")

                if not level:
                    msg = f"CourseMusicDataInfo of type {ty} (from {course_path}) does not have a level set"
                    raise ValueError(msg)

                inserted_course_tracks.append(
                    {
                        "course_id": course_id,
                        "track": i + 1,
                        "level": level[2:],  # Chop off the "Lv" prefix
                    }
                )
            elif ty == 2:
                inserted_course_tracks.append(
                    {"course_id": course_id, "track": i + 1, "level": None}
                )

                for music in info.findall(
                    "./selectMusicList/musicList/list/CourseMusicListSubData"
                ):
                    sub_ty = gettext(music, "./type")

                    if sub_ty != "0":
                        msg = f"Invalid type {sub_ty} for CourseMusicListSubData"
                        raise ValueError(msg)

                    song_id = gettext(music, "./courseMusicData/name/id")
                    difficulty = gettext(music, "./courseMusicData/diff/data")

                    if song_id is None or song_id == "-1" or not difficulty:
                        msg = f"CourseMusicListSubData of type {sub_ty} (from {course_path}) does not have a courseMusicData set"
                        raise ValueError(msg)

                    inserted_course_track_charts.append(
                        {
                            "course_id": course_id,
                            "track": i + 1,
                            "song_id": int(song_id),
                            "difficulty": "WE"
                            if difficulty == "WORLD'S END"
                            else difficulty[:3],
                        }
                    )
            else:
                msg = f"Invalid type {ty} for CourseMusicDataInfo"
                raise ValueError(msg)

    async with async_session() as session, session.begin():
        logger.info(
            "Upserting %d songs, %d charts, %d courses",
            len(inserted_songs),
            len(inserted_charts),
            len(inserted_courses),
        )

        insert_stmt = insert(Song)
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[Song.id],
            set_={
                "title": insert_stmt.excluded.title,
                "chunithm_catcode": insert_stmt.excluded.chunithm_catcode,
                "genre": insert_stmt.excluded.genre,
                "artist": insert_stmt.excluded.artist,
                "release": func.coalesce(insert_stmt.excluded.release, Song.release),
                "version": insert_stmt.excluded.version,
                "bpm": func.coalesce(insert_stmt.excluded.bpm, Song.bpm),
                "min_bpm": func.coalesce(insert_stmt.excluded.min_bpm, Song.min_bpm),
                "max_bpm": func.coalesce(insert_stmt.excluded.max_bpm, Song.max_bpm),
                # also ignore jackets
                "available": Song.available,
                # also ignore removed state
            },
        )

        await session.execute(upsert_stmt, inserted_songs)

        insert_stmt = insert(Chart)
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[Chart.song_id, Chart.difficulty],
            set_={
                "level": insert_stmt.excluded.level,
                "const": insert_stmt.excluded.const,
                "maxcombo": insert_stmt.excluded.maxcombo,
                "tap": insert_stmt.excluded.tap,
                "hold": insert_stmt.excluded.hold,
                "slide": insert_stmt.excluded.slide,
                "air": insert_stmt.excluded.air,
                "flick": insert_stmt.excluded.flick,
                "charter": insert_stmt.excluded.charter,
            },
        )

        await session.execute(upsert_stmt, inserted_charts)

        if len(inserted_courses) > 0:
            insert_stmt = insert(Course)
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=[Course.id],
                set_={
                    k: getattr(insert_stmt.excluded, k)
                    for k in (
                        "cls",
                        "name",
                        "version",
                        "is_duplicate_track_allowed",
                        "life",
                        "recovery_life",
                        "clear_life",
                        "damage_miss",
                        "damage_attack",
                        "damage_justice",
                        "damage_jcrit",
                    )
                },
            )

            await session.execute(upsert_stmt, inserted_courses)

        if len(inserted_course_tracks) > 0:
            insert_stmt = insert(CourseTrack)
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=[CourseTrack.course_id, CourseTrack.track],
                set_={
                    "level": insert_stmt.excluded.level,
                },
            )

            await session.execute(upsert_stmt, inserted_course_tracks)

            await session.execute(
                delete(course_track_charts).where(
                    (course_track_charts.c.course_id + course_track_charts.c.track).in_(
                        {c["course_id"] + c["track"] for c in inserted_course_tracks}
                    )
                )
            )
            await session.execute(
                insert(course_track_charts), inserted_course_track_charts
            )
