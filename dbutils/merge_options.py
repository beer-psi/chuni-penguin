import concurrent.futures
import csv
import itertools
import subprocess
from pathlib import Path
import traceback
from typing import Optional, overload
from xml.etree import ElementTree

import httpx
from PIL import Image
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.stdlib import BoundLogger

from chunithm_net.models.enums import Difficulty
from database.models import Chart, Song
from utils.constants import ASSETS_DIR

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
    Difficulty.BASIC: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_0.png"),
    Difficulty.ADVANCED: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_1.png"),
    Difficulty.EXPERT: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_2.png"),
    Difficulty.MASTER: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_3.png"),
    Difficulty.ULTIMA: lambda: Image.open(ASSETS_DIR / "b50" / "b50_base_4.png"),
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


def extract_jacket(song_id: int, jacket_file: Path, alt_suffix: str = ""):
    try:
        with Image.open(jacket_file) as im:
            im = im.convert("RGB")
            im.save(
                ASSETS_DIR / "jackets" / f"{song_id}{alt_suffix}.png",
                format="PNG",
                optimize=True,
            )

            # world's ends arent going to show up in b50 anytime soon
            if song_id >= 8000:
                return

            im_small = im.resize(
                (B30_JACKET_WIDTH, B30_JACKET_HEIGHT), Image.Resampling.LANCZOS
            )

            # pregenerate jacket art merged with b50 base
            for difficulty in Difficulty:
                if difficulty == Difficulty.WORLDS_END:
                    continue

                with B30_BASE_IMAGES[difficulty]() as b30_base_image:
                    b30_base_image.paste(im_small, (10, 60))
                    b30_base_image.save(
                        ASSETS_DIR
                        / "jackets"
                        / f"{song_id}{alt_suffix}_{difficulty.value}.png",
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
    async with httpx.AsyncClient() as client:
        songlist = (
            await client.get("https://chunithm.sega.jp/storage/json/music.json")
        ).json()
        jacket_by_id = {int(x["id"]): x["image"] for x in songlist}

    if extract_jackets:
        (ASSETS_DIR / "jackets").mkdir(exist_ok=True, parents=True)

    if extract_audios:
        (ASSETS_DIR / "audio").mkdir(exist_ok=True, parents=True)

    xml_paths = data_dir.glob("**/music/**/Music.xml")
    cue_file_paths = data_dir.glob("**/cueFile/**/CueFile.xml")

    if option_dir is not None:
        xml_paths = itertools.chain(
            xml_paths,
            option_dir.glob("**/music/**/Music.xml"),
        )
        cue_file_paths = itertools.chain(
            cue_file_paths, option_dir.glob("**/cueFile/**/CueFile.xml")
        )

    inserted_songs = []
    inserted_charts = []

    with concurrent.futures.ProcessPoolExecutor() as pool:
        for xml_path in xml_paths:
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

                    if cytus2_alt.exists():
                        pool.submit(
                            extract_jacket,
                            song_id_int,
                            cytus2_alt,
                            "_cytus2",
                        )

                    if vividstasis_alt.exists():
                        pool.submit(
                            extract_jacket,
                            song_id_int,
                            vividstasis_alt,
                            "_vividstasis",
                        )

                    if musedash_alt.exists():
                        pool.submit(
                            extract_jacket,
                            song_id_int,
                            musedash_alt,
                            "_musedash",
                        )

                    if musicdiver_alt.exists():
                        pool.submit(
                            extract_jacket,
                            song_id_int,
                            musicdiver_alt,
                            "_musicdiver",
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

    async with async_session() as session, session.begin():
        logger.info(
            "Upserting %d songs and %d charts",
            len(inserted_songs),
            len(inserted_charts),
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
