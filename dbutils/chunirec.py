import re
from datetime import datetime
from logging import Logger
from typing import Literal, Optional

import aiohttp
import msgspec
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chunithm_net.consts import INTERNATIONAL_JACKET_BASE, JACKET_BASE
from database.models import Chart, Song, SongJacket
from utils import TOKYO_TZ, release_to_chunithm_version
from utils.config import config
from utils.types.errors import MissingConfiguration


class ChunirecMeta(msgspec.Struct):
    id: str
    title: str
    genre: str
    artist: str
    release: str
    bpm: int


class ChunirecDifficulty(msgspec.Struct):
    level: float
    const: float
    maxcombo: int
    is_const_unknown: int


class ChunirecSong(msgspec.Struct):
    meta: ChunirecMeta
    data: dict[Literal["BAS", "ADV", "EXP", "MAS", "ULT", "WE"], ChunirecDifficulty]


class ZetarakuNoteCounts(msgspec.Struct):
    tap: Optional[int]
    hold: Optional[int]
    slide: Optional[int]
    air: Optional[int]
    flick: Optional[int]
    total: Optional[int]


class ZetarakuSheet(msgspec.Struct, rename="camel"):
    difficulty: str
    level: str
    level_value: float
    internal_level: Optional[str]
    internal_level_value: float
    note_designer: Optional[str]
    note_counts: dict[
        Literal["tap", "hold", "slide", "air", "flick", "total"], Optional[int]
    ]
    regions: dict[str, bool]


class ZetarakuSong(msgspec.Struct, rename="camel"):
    title: str
    category: str
    image_name: str
    version: Optional[str]
    bpm: Optional[int]
    sheets: list[ZetarakuSheet]


class ZetarakuChunithmData(msgspec.Struct):
    songs: list[ZetarakuSong]


class ChunithmOfficialSong(msgspec.Struct):
    id: int
    catname: str
    newflag: int
    title: str
    reading: str
    artist: str
    lev_bas: str
    lev_adv: str
    lev_exp: str
    lev_mas: str
    lev_ult: str
    we_kanji: str
    we_star: str
    image: str


class MaimaiOfficialSong(msgspec.Struct):
    artist: str
    catcode: str
    image_url: str
    release: str
    lev_bas: str
    lev_adv: str
    lev_exp: str
    lev_mas: str
    sort: str
    title: str
    title_kana: str
    version: str
    lev_remas: str | None = None


NOTE_TYPES: list[Literal["tap", "hold", "slide", "air", "flick"]] = [
    "tap",
    "hold",
    "slide",
    "air",
    "flick",
]
CHUNITHM_CATCODES = {
    "POPS & ANIME": 0,
    "POPS&ANIME": 0,
    "niconico": 2,
    "東方Project": 3,
    "VARIETY": 6,
    "イロドリミドリ": 7,
    "ゲキマイ": 9,
    "ORIGINAL": 5,
    # Not a real CHUNITHM category, but used for normalization purposes
    # when matching songs between chunirec and zetaraku
    "WORLD'S END": 255,
}

MANUAL_MAPPINGS: dict[str, dict[str, str]] = {
    "7a561ab609a0629d": {  # Trackless wilderness【狂】
        "id": "8227",
        "catname": "ORIGINAL",
        "newflag": "0",
        "title": "Trackless wilderness",
        "reading": "TRACKLESSWILDERNESS",
        "artist": "Noah",
        "lev_bas": "",
        "lev_adv": "",
        "lev_exp": "",
        "lev_mas": "",
        "lev_ult": "",
        "we_kanji": "狂",
        "we_star": "7",
        "image": "629be924b3383e08.jpg",
    },
    "e6605126a95c4c8d": {  # Trrricksters!!【狂】
        "id": "8228",
        "catname": "ORIGINAL",
        "newflag": "0",
        "title": "Trrricksters!!",
        "reading": "TRRRICKSTERS",
        "artist": "s-don vs. 翡乃イスカ",
        "lev_bas": "",
        "lev_adv": "",
        "lev_exp": "",
        "lev_mas": "",
        "lev_ult": "",
        "we_kanji": "狂",
        "we_star": "9",
        "image": "7615de9e9eced518.jpg",
    },
    "6502b8cb896a3108": {
        "id": "8025",
        "catname": "イロドリミドリ",
        "title": "Help me, あーりん!",
        "reading": "HELPMEアウリン",
        "artist": "イロドリミドリ",
        "lev_bas": "",
        "lev_adv": "",
        "lev_exp": "",
        "lev_mas": "",
        "lev_ult": "",
        "we_kanji": "嘘",
        "we_star": "5",
        "image": "c1ff8df1757fedf4.jpg",
    },
    "98baa8dadec9674a": {
        "id": "8078",
        "catname": "イロドリミドリ",
        "title": "あねぺったん",
        "reading": "アネヘツタン",
        "artist": "月鈴姉妹(イロドリミドリ)",
        "lev_bas": "",
        "lev_adv": "",
        "lev_exp": "",
        "lev_mas": "",
        "lev_ult": "",
        "we_kanji": "嘘",
        "we_star": "7",
        "image": "a6889b8a729210be.jpg",
    },
    "108fb090064d84eb": {
        "id": "8116",
        "catname": "イロドリミドリ",
        "title": "イロドリミドリ杯花映塚全一決定戦公式テーマソング『ウソテイ』",
        "reading": "イロトリミトリハイカエイツカセンイチケツテイセンコウシキテウマソンクウソテイ",
        "artist": "イロドリミドリ",
        "lev_bas": "",
        "lev_adv": "",
        "lev_exp": "",
        "lev_mas": "",
        "lev_ult": "",
        "we_kanji": "嘘",
        "we_star": "7",
        "image": "43bd6cbc31e4c02c.jpg",
    },
    "1ce51015f2293d1a": {
        "id": "8281",
        "catname": "ORIGINAL",
        "title": "Parad'ox",
        "reading": "PARADOX",
        "artist": "Potwi",
        "lev_bas": "",
        "lev_adv": "",
        "lev_exp": "",
        "lev_mas": "",
        "lev_ult": "",
        "we_kanji": "狂",
        "we_star": "9",
        "image": "20b8716a15c1b551.jpg",
    },
    "67be895064262b87": {
        "id": "8282",
        "catname": "ORIGINAL",
        "title": "otorii INNOVATED -[i]3-",
        "reading": "OTORIIINNOVATEDI3",
        "artist": "NAOKI underground",
        "lev_bas": "",
        "lev_adv": "",
        "lev_exp": "",
        "lev_mas": "",
        "lev_ult": "",
        "we_kanji": "狂",
        "we_star": "9",
        "image": "41d003f64f1b3b86.jpg",
    },
}
for idx, random in enumerate(
    # Random WE, A through F
    [
        ("d8b8af2016eec2f0", "97af9ed62e768d73.jpg"),
        ("5a0bc7702113a633", "fd4a488ed2bc67d8.jpg"),
        ("948e0c4b67f4269d", "ce911dfdd8624a7c.jpg"),
        ("56e583c091b4295c", "6a3201f1b63ff9a3.jpg"),
        ("49794fec968b90ba", "d43ab766613ba19e.jpg"),
        ("b9df9d9d74b372d9", "4a359278c6108748.jpg"),
    ]
):
    random_id, random_image = random
    MANUAL_MAPPINGS[random_id] = {
        "id": str(8244 + idx),
        "catname": "VARIETY",
        "title": "Random",
        "reading": "RANDOM",
        "artist": "Sobrem × Silentroom",  # noqa: RUF001
        "lev_bas": "",
        "lev_adv": "",
        "lev_exp": "",
        "lev_mas": "",
        "lev_ult": "",
        "we_kanji": f"分{chr(65 + idx)}",
        "we_star": "5",
        "image": random_image,
    }

WORLD_END_REGEX = re.compile(r"【(.{1,2})】$", re.MULTILINE)


def normalize_title(title: str, *, remove_we_kanji: bool = False) -> str:
    if title == "Help me, ERINNNNNN!!":
        title = "Help me, ERINNNNNN!!（Band ver.）"  # noqa: RUF001

    title = (
        title.lower()
        .replace(" ", " ")
        .replace("　", " ")
        .replace(" ", " ")
        .replace(":", ":")
        .replace("(", "(")
        .replace(")", ")")
        .replace("!", "!")
        .replace("?", "?")
        .replace("`", "'")
        .replace("`", "'")
        .replace("”", '"')
        .replace("“", '"')
        .replace("~", "~")
        .replace("-", "-")
        .replace("@", "@")
    )
    if remove_we_kanji:
        title = WORLD_END_REGEX.sub("", title)
    return title


async def update_db(logger: Logger, async_session: async_sessionmaker[AsyncSession]):
    token = config.credentials.chunirec_token
    if token is None:
        msg = "credentials.chunirec_token"
        raise MissingConfiguration(msg)

    async with aiohttp.ClientSession() as client:
        resp = await client.get(
            f"https://api.chunirec.net/2.0/music/showall.json?token={token}&region=jp2"
        )
        chuni_resp = await client.get(
            "https://chunithm.sega.jp/storage/json/music.json"
        )
        maimai_resp = await client.get(
            "https://maimai.sega.jp/data/maimai_songs.json",
        )
        zetaraku_resp = await client.get(
            "https://dp4p6x0xfi5o9.cloudfront.net/chunithm/data.json"
        )
        songs = msgspec.json.decode(await resp.read(), type=list[ChunirecSong])
        chuni_songs = msgspec.json.decode(
            await chuni_resp.read(),
            type=list[ChunithmOfficialSong],
            strict=False,  # in the official dataset, the id is a string of digits
        )
        maimai_songs = msgspec.json.decode(
            await maimai_resp.read(), type=list[MaimaiOfficialSong]
        )
        zetaraku_songs = msgspec.json.decode(
            await zetaraku_resp.read(), type=ZetarakuChunithmData
        )

    inserted_songs = []
    inserted_charts = []
    inserted_jackets = []
    for song in songs:
        chunithm_id = -1
        chunithm_catcode = -1
        jacket = ""
        try:
            if song.meta.id in MANUAL_MAPPINGS:
                chunithm_song = msgspec.convert(
                    MANUAL_MAPPINGS[song.meta.id], ChunithmOfficialSong
                )
            elif song.data.get("WE") is None:
                chunithm_song = next(
                    x
                    for x in chuni_songs
                    if normalize_title(x.title) == normalize_title(song.meta.title)
                    and CHUNITHM_CATCODES[x.catname]
                    == CHUNITHM_CATCODES[song.meta.genre]
                )
            else:
                chunithm_song = next(
                    x
                    for x in chuni_songs
                    if normalize_title(f"{x.title}【{x.we_kanji}】")
                    == normalize_title(song.meta.title)
                )
            chunithm_id = chunithm_song.id
            chunithm_catcode = int(CHUNITHM_CATCODES[chunithm_song.catname])
            jacket = chunithm_song.image
        except StopIteration:
            logger.warning(f"Couldn't find {song.meta}")
            continue

        if not jacket:
            chunithm_song_no_we = next(
                (
                    x
                    for x in chuni_songs
                    if normalize_title(x.title)
                    == normalize_title(song.meta.title, remove_we_kanji=True)
                    and normalize_title(x.artist) == normalize_title(song.meta.artist)
                ),
                None,
            )
            jacket = chunithm_song_no_we.image if chunithm_song_no_we else None

        zetaraku_song = next(
            (
                x
                for x in zetaraku_songs.songs
                if normalize_title(x.title) == normalize_title(song.meta.title)
                and CHUNITHM_CATCODES[x.category] == CHUNITHM_CATCODES[song.meta.genre]
            ),
            None,
        )
        maimai_song = next(
            (
                x
                for x in maimai_songs
                if normalize_title(x.title) == normalize_title(song.meta.title)
            ),
            None,
        )

        version = None

        if zetaraku_song is not None:
            version = zetaraku_song.version
        if version is None:
            release_date = datetime.strptime(song.meta.release, "%Y-%m-%d").astimezone(
                TOKYO_TZ
            )
            version = release_to_chunithm_version(release_date)
        inserted_song = {
            "id": chunithm_id,
            # Don't use song["meta"]["title"]
            "title": chunithm_song.title,
            "chunithm_catcode": chunithm_catcode,
            "genre": song.meta.genre,
            "artist": song.meta.artist,
            "release": song.meta.release,
            "version": version,
            "bpm": None if song.meta.bpm == 0 else song.meta.bpm,
            "jacket": jacket,
            "available": (
                int(zetaraku_song.sheets[0].regions.get("intl", False))
                if zetaraku_song is not None and len(zetaraku_song.sheets) > 1
                else 0
            ),
            "removed": (
                int(not zetaraku_song.sheets[0].regions.get("jp", False))
                if zetaraku_song is not None and len(zetaraku_song.sheets) > 1
                else 0
            ),
        }

        if inserted_song["bpm"] is None and zetaraku_song is not None:
            inserted_song["bpm"] = zetaraku_song.bpm

        inserted_songs.append(inserted_song)
        inserted_jackets.append(
            {"song_id": chunithm_id, "jacket_url": f"{JACKET_BASE}/{jacket}"}
        )
        inserted_jackets.append(
            {
                "song_id": chunithm_id,
                "jacket_url": f"{INTERNATIONAL_JACKET_BASE}/{jacket}",
            }
        )
        if maimai_song is not None:
            inserted_jackets.extend(
                [
                    {
                        "song_id": chunithm_id,
                        "jacket_url": f"https://{domain}/maimai-mobile/img/Music/{maimai_song.image_url}",
                    }
                    for domain in {"maimaidx-eng.com", "maimaidx.jp"}
                ]
            )
        if zetaraku_song is not None:
            inserted_jackets.append(
                {
                    "song_id": chunithm_id,
                    "jacket_url": f"https://dp4p6x0xfi5o9.cloudfront.net/chunithm/img/cover/{zetaraku_song.image_name}",
                }
            )

        for difficulty, chart in song.data.items():
            if difficulty == "WE":
                continue

            if 0 < chart.level <= 9.5:
                chart.const = chart.level
                chart.is_const_unknown = 0

            inserted_chart = {
                "song_id": chunithm_id,
                "difficulty": difficulty,
                "level": str(chart.level).replace(".5", "+").replace(".0", ""),
                "const": None if chart.is_const_unknown == 1 else chart.const,
                "maxcombo": chart.maxcombo if chart.maxcombo != 0 else None,
                "tap": None,
                "hold": None,
                "slide": None,
                "air": None,
                "flick": None,
                "charter": None,
            }

            if (
                zetaraku_song is not None
                and (
                    zetaraku_sheet := next(
                        (
                            sheet
                            for sheet in zetaraku_song.sheets
                            if sheet.difficulty[:3] == difficulty.lower()
                        ),
                        None,
                    )
                )
                is not None
            ):
                inserted_chart["charter"] = zetaraku_sheet.note_designer
                if inserted_chart["charter"] == "-":
                    inserted_chart["charter"] = None

                total = 0
                should_add_notecounts = True
                for note_type in NOTE_TYPES:
                    count = zetaraku_sheet.note_counts[note_type]
                    if count is None and note_type != "flick":
                        should_add_notecounts = False
                        break

                    inserted_chart[note_type] = count or 0
                    total += count or 0

                if should_add_notecounts:
                    inserted_chart["maxcombo"] = inserted_chart["maxcombo"] or total
                else:
                    # Unset everything that was set
                    for note_type in NOTE_TYPES:
                        inserted_chart[note_type] = None

            inserted_charts.append(inserted_chart)

        if (chart := song.data.get("WE")) is not None:
            if len(chunithm_song.we_star) < 1:
                logger.warning(
                    f"matching chunithm_song of {song.meta.id} is not a world's end song: {chunithm_song}"
                )
                continue

            we_stars = ""
            for _ in range(-1, int(chunithm_song.we_star), 2):
                we_stars += "☆"
            inserted_charts.append(
                {
                    "song_id": chunithm_id,
                    "difficulty": "WE",
                    "level": chunithm_song.we_kanji + we_stars,
                    "const": None,
                    "maxcombo": chart.maxcombo if chart.maxcombo != 0 else None,
                    "tap": None,
                    "hold": None,
                    "slide": None,
                    "air": None,
                    "flick": None,
                    "charter": None,
                }
            )

    async with async_session() as session, session.begin():
        insert_statement = insert(Song)
        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=[Song.id],
            set_={
                "title": insert_statement.excluded.title,
                "chunithm_catcode": insert_statement.excluded.chunithm_catcode,
                "genre": insert_statement.excluded.genre,
                "artist": insert_statement.excluded.artist,
                "release": insert_statement.excluded.release,
                "version": insert_statement.excluded.version,
                "bpm": func.coalesce(insert_statement.excluded.bpm, Song.bpm),
                "jacket": func.coalesce(insert_statement.excluded.jacket, Song.jacket),
                "available": insert_statement.excluded.available,
                "removed": insert_statement.excluded.removed,
            },
        )
        await session.execute(upsert_statement, inserted_songs)

        insert_statement = insert(Chart)
        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=[Chart.song_id, Chart.difficulty],
            set_={
                "level": insert_statement.excluded.level,
                "const": insert_statement.excluded.const,
                "maxcombo": func.coalesce(
                    insert_statement.excluded.maxcombo, Chart.maxcombo
                ),
                "tap": func.coalesce(insert_statement.excluded.tap, Chart.tap),
                "hold": func.coalesce(insert_statement.excluded.hold, Chart.hold),
                "slide": func.coalesce(insert_statement.excluded.slide, Chart.slide),
                "air": func.coalesce(insert_statement.excluded.air, Chart.air),
                "flick": func.coalesce(insert_statement.excluded.flick, Chart.flick),
                "charter": func.coalesce(
                    insert_statement.excluded.charter, Chart.charter
                ),
            },
        )
        await session.execute(upsert_statement, inserted_charts)

        insert_statement = insert(SongJacket)
        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=[SongJacket.jacket_url],
            set_={
                "song_id": insert_statement.excluded.song_id,
            },
        )
        await session.execute(upsert_statement, inserted_jackets)
