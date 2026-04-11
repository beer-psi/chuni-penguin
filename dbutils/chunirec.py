import json
import re
from typing import Literal, Optional

import aiohttp
import msgspec
from structlog.stdlib import BoundLogger

from chuni_penguin.config import config
from chuni_penguin.errors import MissingConfiguration

from .seeds import SEEDS_DIR, SeedsJSONEncoder


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
    branch: str | msgspec.UnsetType = msgspec.UNSET


class MaimaiOfficialSong(msgspec.Struct):
    image_url: str
    title: str
    artist: str


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
        "chunirec_id": "7a561ab609a0629d",
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
        "chunirec_id": "e6605126a95c4c8d",
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
        "chunirec_id": "6502b8cb896a3108",
        "catname": "イロドリミドリ",
        "newflag": "0",
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
        "chunirec_id": "98baa8dadec9674a",
        "catname": "イロドリミドリ",
        "newflag": "0",
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
        "chunirec_id": "108fb090064d84eb",
        "catname": "イロドリミドリ",
        "newflag": "0",
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
        "chunirec_id": "1ce51015f2293d1a",
        "catname": "ORIGINAL",
        "newflag": "0",
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
        "chunirec_id": "67be895064262b87",
        "catname": "ORIGINAL",
        "newflag": "0",
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
        ("d8b8af2016eec2f0", "97af9ed62e768d73.jpg", "LASTMORN"),
        ("5a0bc7702113a633", "fd4a488ed2bc67d8.jpg", "Implexrough"),
        ("948e0c4b67f4269d", "ce911dfdd8624a7c.jpg", "Shannon's Theorem"),
        ("56e583c091b4295c", "6a3201f1b63ff9a3.jpg", "Just Say It"),
        ("49794fec968b90ba", "d43ab766613ba19e.jpg", "2anyFirst"),
        ("b9df9d9d74b372d9", "4a359278c6108748.jpg", "Alt Futur"),
    ]
):
    random_id, random_image, random_branch = random
    MANUAL_MAPPINGS[random_id] = {
        "id": str(8244 + idx),
        "chunirec_id": random_id,
        "catname": "VARIETY",
        "newflag": "0",
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
        "branch": random_branch,
        "image": random_image,
    }

WORLD_END_REGEX = re.compile(r"【(.{1,2})】$", re.MULTILINE)


def normalize_title(title: str, *, remove_we_kanji: bool = False) -> str:
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


async def update_db(logger: BoundLogger):
    token = config.credentials.chunirec_token

    if token is None:
        msg = "credentials.chunirec_token"
        raise MissingConfiguration(msg)

    with (SEEDS_DIR / "songs.json").open("rb") as f:
        songs = msgspec.json.decode(f.read())

    async with aiohttp.ClientSession() as client:
        resp = await client.get(
            f"https://api.chunirec.net/2.0/music/showall.json?token={token}&region=jp2"
        )
        chunirec_songs = msgspec.json.decode(await resp.read(), type=list[ChunirecSong])

    for chunirec_song in chunirec_songs:
        if chunirec_song.meta.id in MANUAL_MAPPINGS:
            song = next(
                (
                    song
                    for song in songs
                    if song["id"] == int(MANUAL_MAPPINGS[chunirec_song.meta.id]["id"])
                ),
                None,
            )
        elif chunirec_song.data.get("WE") is not None:
            song = next(
                (
                    song
                    for song in songs
                    if song["id"] >= 8000
                    and not song["removed"]
                    and len(song["charts"]) == 1
                    and song["charts"][0]["difficulty"] == "WE"
                    and normalize_title(
                        f"{song['title']}【{song['charts'][0]['level'][:1]}】"
                    )
                    == normalize_title(chunirec_song.meta.title)
                )
            )
        else:
            song = next(
                (
                    song
                    for song in songs
                    if not song["removed"]
                    and normalize_title(song["title"])
                    == normalize_title(chunirec_song.meta.title)
                    and song["chunithm_catcode"]
                    == CHUNITHM_CATCODES[chunirec_song.meta.genre]
                ),
                None,
            )

        if song is not None:
            song["chunirec_id"] = chunirec_song.meta.id
        else:
            logger.warning(
                "Could not find matching seeds entry",
                chunirec_id=chunirec_song.meta.id,
                title=chunirec_song.meta.title,
                genre=chunirec_song.meta.genre,
            )

    with (SEEDS_DIR / "songs.json").open("w") as f:
        json.dump(
            songs,
            f,
            cls=SeedsJSONEncoder,
            indent=4,
            ensure_ascii=False,
        )
