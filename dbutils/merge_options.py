import csv
import itertools
from logging import Logger
from pathlib import Path
from typing import Optional, overload
from xml.etree import ElementTree

from PIL import Image
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import Chart, Song

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
]
ASSETS_DIR = Path(__file__).parent.parent / "assets"


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


async def merge_options(
    logger: Logger,
    async_session: async_sessionmaker[AsyncSession],
    data_dir: Path,
    option_dir: Optional[Path],
    *,
    extract_jackets: bool,
):
    if extract_jackets:
        (ASSETS_DIR / "jackets").mkdir(exist_ok=True, parents=True)

    xml_paths = data_dir.glob("**/music/**/Music.xml")

    if option_dir is not None:
        xml_paths = itertools.chain(
            xml_paths,
            option_dir.glob("**/music/**/Music.xml"),
        )

    inserted_songs = []
    inserted_charts = []

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

        if extract_jackets:
            jacket_file = gettext(root, "./jaketFile/path")

            if not jacket_file:
                continue

            with Image.open(xml_path.parent / jacket_file) as im:
                im.save(
                    ASSETS_DIR / "jackets" / f"{int(song_id)}.png",
                    format="PNG",
                    optimize=True,
                )

        if we_tag_name != "Invalid":
            genre = "WORLD'S END"

        release_date = gettext(root, "./releaseDate")

        inserted_song = {
            "id": int(song_id),
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
            "jacket": None,
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
                star_dif_type = int(gettext(root, "./starDifType", "0"))
                displayed_level = we_tag_name

                for _ in range(-1, star_dif_type, 2):
                    displayed_level += "☆"

                const = None
            else:
                displayed_level = level_str + ("+" if level_decimal >= 50 else "")
                const = float(f"{level_str}.{level_decimal_str}")

            inserted_chart = {
                "song_id": int(song_id),
                "difficulty": "WE" if difficulty == "WORLD'S END" else difficulty[:3],
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
                "available": insert_stmt.excluded.available,
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
