# ruff: noqa: RUF001

import importlib.util
import re
from html import unescape
from logging import Logger

import aiohttp
from bs4 import BeautifulSoup
from bs4.element import Comment
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import Chart, SdvxinChartView, Song

WORLD_END_SDVXIN_REGEX = re.compile(
    r"document\.title\s*=\s*['\"](?P<title>.+?) \[WORLD'S END(?:\])?\s*(?P<difficulty>.+?)(?:\]\s*)?['\"]"
)
SDVXIN_CATEGORIES = [
    "pops",
    "niconico",
    "toho",
    "variety",
    "irodorimidori",
    "gekimai",
    "original",
    "ultima",
    "end",
]
SDVXIN_DIFFICULTY_MAPPING = {
    "B": "BAS",
    "A": "ADV",
    "E": "EXP",
    "M": "MAS",
    "U": "ULT",
    "W": "WE",
}
TITLE_MAPPING = {
    "AstroNotes.": "AstrøNotes.",
    "Athlete Killer ”Meteor”": 'Athlete Killer "Meteor"',
    "Aventyr": "Äventyr",
    "Blow my mind": "Blow My Mind",
    "Chaotic Order": "Chaotic Ørder",
    "DAZZLING SEASON": "DAZZLING♡SEASON",
    "DON`T STOP ROCKIN` ~[O_O] MIX~": "D✪N`T ST✪P R✪CKIN` ~[✪_✪] MIX~",
    "DON’T STOP ROCKIN’ ～[O_O] MIX": "D✪N’T ST✪P R✪CKIN’ ～[✪_✪] MIX～",
    "DON’T STOP ROCKIN’ ～[O_O] MIX～": "D✪N’T ST✪P R✪CKIN’ ～[✪_✪] MIX～",
    "Daydream cafe": "Daydream café",
    "Defandour": "Dèfandour",
    "ECHO-": "ECHO",
    "Excalibur": "Excalibur ～Revived resolution～",
    "Excalibur ~Revived resolution~": "Excalibur ～Revived resolution～",
    "GO!GO!ラブリズム ~あーりん書類審査通過記念Ver.~": "GO!GO!ラブリズム♥ ~あーりん書類審査通過記念Ver.~",
    "GRANDIR": "GRÄNDIR",
    "Give me Love?": "Give me Love♡",
    "GranFatalite": "GranFatalité",
    "Help,me あーりん!": "Help me, あーりん!",
    "Help,me あーりん！": "Help me, あーりん！",
    "Help me, ERINNNNNN!!": "Help me, ERINNNNNN!!（Band ver.）",  # The song was renamed by request of the rights holder.
    "In The Blue Sky `01": "In The Blue Sky '01",
    "In The Blue Sky ’01": "In The Blue Sky '01",
    "Jorqer": "Jörqer",
    "L'epilogue": "L'épilogue",
    "Little ”Sister” Bitch": 'Little "Sister" Bitch',
    "Love's Theme of BADASS": "Love's Theme of BADASS ～バッド・アス 愛のテーマ～",
    "Make Up Your World": "Make Up Your World feat. キョンシーのCiちゃん & らっぷびと",
    "Mass Destruction (''P3'' + ''P3F'' ver.)": 'Mass Destruction ("P3" + "P3F" ver.)',
    "NYAN-NYA, More! ラブシャイン、Chu?": "NYAN-NYA, More! ラブシャイン、Chu♥",
    "Okeanos": "Ωκεανος",
    "Pump": "Pump!n",
    "Ray ?はじまりのセカイ?": "Ray ―はじまりのセカイ― (クロニクルアレンジver.)",
    "Reach for the Stars": "Reach For The Stars",
    "Session High": "Session High⤴",
    "Seyana": "Seyana. ～何でも言うことを聞いてくれるアカネチャン～",
    "Seyana. ~何でも言うことを聞いてくれるアカネチャン~": "Seyana. ～何でも言うことを聞いてくれるアカネチャン～",
    "solips": "sølips",
    "Solstand": "Solstånd",
    "Super Lovely": "Super Lovely (Heavenly Remix)",
    "The Metaverse": "The Metaverse -First story of the SeelischTact-",
    "Tuatha De Danann": "Tuatha Dé Danann",
    "Walzer fur das Nichts": "Walzer für das Nichts",
    "Yet Another ''drizzly rain''": "Yet Another ”drizzly rain”",
    "ouroboros": "ouroboros -twin stroke of the end-",
    "”STAR”T": '"STAR"T',
    "まっすぐ→→→ストリーム!": "まっすぐ→→→ストリーム！",
    "めっちゃ煽ってくる": "めっちゃ煽ってくるタイプの音ゲーボス曲ちゃんなんかに負けないが？？？？？",
    "めいど・うぃず・どらごんず": "めいど・うぃず・どらごんず♥",
    "イロドリミドリ杯 花映塚全一決定戦公式テーマソング『ウソテイ』": "イロドリミドリ杯花映塚全一決定戦公式テーマソング『ウソテイ』",
    "キュアリアス光吉古牌\u3000-祭-": "キュアリアス光吉古牌\u3000－祭－",
    "キュアリアス光吉古牌\u3000?祭?": "キュアリアス光吉古牌\u3000－祭－",
    "チルノおかん": "チルノおかんのさいきょう☆バイブスごはん",
    "モンダイナイトリッパー": "モンダイナイトリッパー！",
    "ナイト・オブ・ナイツ (かめりあ`s“": "ナイト・オブ・ナイツ (かめりあ`s“ワンス・アポン・ア・ナイト”Remix)",
    "ナイト・オブ・ナイツ (かめりあ’s“": "ナイト・オブ・ナイツ (かめりあ’s“ワンス・アポン・ア・ナイト”Remix)",
    "ラブって?ジュエリー♪えんじぇる☆ブレイク!!": "ラブって♡ジュエリー♪えんじぇる☆ブレイク!!",
    "ラブって?ジュエリー♪えんじぇる☆ブレイク！！": "ラブって♡ジュエリー♪えんじぇる☆ブレイク！！",
    "一世嬉遊曲": "一世嬉遊曲‐ディヴェルティメント‐",
    "一世嬉遊曲-ディヴェルティメント-": "一世嬉遊曲‐ディヴェルティメント‐",
    "今ぞ崇め奉れ☆オマエらよ!!~姫の秘メタル渇望~": "今ぞ♡崇め奉れ☆オマエらよ!!~姫の秘メタル渇望~",
    "今ぞ崇め奉れ☆オマエらよ！！～姫の秘メタル渇望～": "今ぞ♡崇め奉れ☆オマエらよ！！～姫の秘メタル渇望～",
    "光線チューニング~なずな": "光線チューニング ~なずな妄想海フェスイメージトレーニングVer.~",
    "光線チューニング～なずな": "光線チューニング ～なずな妄想海フェスイメージトレーニングVer.～",
    "多重未来のカルテット": "多重未来のカルテット -Quartet Theme-",
    "失礼しますが、RIP": "失礼しますが、RIP♡",
    "崩壊歌姫": "崩壊歌姫 -disruptive diva-",
    "男装女形表裏一体発狂小娘": "男装女形表裏一体発狂小娘の詐称疑惑と苦悩と情熱。",
    "砂漠のハンティングガール": "砂漠のハンティングガール♡",
    "私の中の幻想的世界観": "私の中の幻想的世界観及びその顕現を想起させたある現実での出来事に関する一考察",
    "萌豚功夫大乱舞": "萌豚♥功夫♥大乱舞",
    "優勝Princess": "優勝Princess♡",
    "ＧＯ！ＧＯ！ラブリズム ～あーりん書類審査通過記念Ver.～": "ＧＯ！ＧＯ！ラブリズム♥ ～あーりん書類審査通過記念Ver.～",
    "《真紅》～ Pavane Pour La Flamme": "《真紅》 ～ Pavane Pour La Flamme",
    "《楽土》～ One and Only One": "《楽土》 ～ One and Only One",
    "《散華》～ EMBARK": "《散華》 ～ EMBARK",
    "《慈雨》～ La Symphonie de Salacia: Agony Movement": "《慈雨》 ～ La Symphonie de Salacia: Agony Movement",
    "《創造》～ Cries, beyond The End": "《創造》 ～ Cries, beyond The End",
    "美少女無罪パイレーツ": "美少女無罪♡パイレーツ",
    "AMARA (大未来電脳)": "ÅMARA (大未来電脳)",
}


async def update_sdvxin(
    logger: Logger, async_session: async_sessionmaker[AsyncSession]
):
    bs4_features = "lxml" if importlib.util.find_spec("lxml") else "html.parser"

    # sdvx.in ID, song_id, difficulty
    inserted_data: list[dict] = []
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=600)
    ) as client, async_session() as session, session.begin():
        # standard categories
        for category in SDVXIN_CATEGORIES:
            logger.info(f"Processing category {category}")
            if category == "end":
                url = "https://sdvx.in/chunithm/end.htm"
            else:
                url = f"https://sdvx.in/chunithm/sort/{category}.htm"
            resp = await client.get(url)
            soup = BeautifulSoup(await resp.text(), bs4_features)

            tables = soup.select("table:has(td.tbgl)")
            if len(tables) == 0:
                logger.error(f"Could not find table(s) for category {category}")
                continue

            for table in tables:
                scripts = table.select("script[src]")

                for script in scripts:
                    title = next(
                        (
                            str(x)
                            for x in script.next_elements
                            if isinstance(x, Comment)
                        ),
                        None,
                    )

                    if title is None:
                        continue

                    title = TITLE_MAPPING.get(title, unescape(title))
                    sdvx_in_id = str(script["src"]).split("/")[-1][
                        :5
                    ]  # TODO: dont assume the ID is always 5 digits

                    stmt = select(Song)
                    condition = Song.title == title
                    script_data = None
                    level = None

                    if category == "end":
                        script_resp = await client.get(
                            f"https://sdvx.in{script['src']}"
                        )
                        script_data = await script_resp.text()

                        match = WORLD_END_SDVXIN_REGEX.search(script_data)
                        if (
                            match is None
                            or (level := match.group("difficulty")) is None
                        ):
                            logger.warning(
                                f"Could not extract difficulty for {title}, {sdvx_in_id}"
                            )
                            continue

                        stmt = stmt.join(Chart)
                        condition &= (Song.id >= 8000) & (Chart.level == level)
                    else:
                        condition &= Song.id < 8000

                    stmt = stmt.where(condition)
                    song = (await session.execute(stmt)).scalar_one_or_none()

                    if song is None:
                        if category == "end":
                            logger.warning("Could not find %s [%s]", title, level)
                        else:
                            logger.warning("Could not find %s", title)

                        continue

                    if script_data is None:
                        script_resp = await client.get(
                            f"https://sdvx.in{script['src']}"
                        )
                        script_data = await script_resp.text()

                    for line in script_data.splitlines():
                        if not line.startswith(f"var LV{sdvx_in_id}"):
                            continue

                        key, value = line.split("=", 1)

                        # var LV00000W
                        # var LV00000W2
                        level = SDVXIN_DIFFICULTY_MAPPING[key[11]]
                        end_index = key[12] if len(key) > 12 else ""
                        value_soup = BeautifulSoup(
                            value.removeprefix('"').removesuffix('";'), bs4_features
                        )

                        if value_soup.select_one("a") is None:
                            continue

                        inserted_data.append(
                            {
                                "id": sdvx_in_id,
                                "song_id": song.id,
                                "difficulty": level,
                                "end_index": end_index,
                            }
                        )

        stmt = insert(SdvxinChartView).on_conflict_do_nothing()
        await session.execute(stmt, inserted_data)
