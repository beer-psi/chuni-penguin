# ruff: noqa: RUF001

import json
import re
from html import unescape

import aiohttp
import msgspec
from selectolax.lexbor import LexborHTMLParser
from structlog.stdlib import BoundLogger

from .seeds import SEEDS_DIR, SeedsJSONEncoder

WORLD_END_SDVXIN_REGEX = re.compile(
    r"document\.title\s*=\s*['\"](?P<title>.+?) \[WORLD'S END(?:\])?\s*(?P<difficulty>.+?)(?:\]\s*)?['\"]"
)
WORLD_END_DIFFICULTY_REGEX = re.compile(
    r"/chunithm/chfiles/chlv/new(?P<kanji>.)(?P<star_difficulty>\d)\.png"
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
    # Don't automatically process WORLD'S ENDs, these are a pain in the ass to
    # process properly, since there can be multiple different entries for a (song, difficulty)
    # tuple.
    # "end",
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
    "BOW AND ARROW（アニメ・オープニングver.）": "BOW AND ARROW （アニメ・オープニングver.）",
    "Chaotic Order": "Chaotic Ørder",
    "chronos": "χρόνος",
    "DAZZLING SEASON": "DAZZLING♡SEASON",
    "DON`T STOP ROCKIN` ~[O_O] MIX~": "D✪N`T ST✪P R✪CKIN` ~[✪_✪] MIX~",
    "DON’T STOP ROCKIN’ ～[O_O] MIX": "D✪N’T ST✪P R✪CKIN’ ～[✪_✪] MIX～",
    "DON’T STOP ROCKIN’ ～[O_O] MIX～": "D✪N’T ST✪P R✪CKIN’ ～[✪_✪] MIX～",
    "Daydream cafe": "Daydream café",
    "Defandour": "Dèfandour",
    "Don't say ”lazy”": 'Don\'t say "lazy"',
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
    "M@GICAL☆CURE! LOVE SHOT!": "M@GICAL☆CURE! LOVE ♥ SHOT!",
    "Make Up Your World": "Make Up Your World feat. キョンシーのCiちゃん & らっぷびと",
    "Mass Destruction (''P3'' + ''P3F'' ver.)": 'Mass Destruction ("P3" + "P3F" ver.)',
    "MegiddO": "MegiddØ",
    "NYAN-NYA, More! ラブシャイン、Chu?": "NYAN-NYA, More! ラブシャイン、Chu♥",
    "Okeanos": "Ωκεανος",
    "Pump": "Pump!n",
    "Ray ?はじまりのセカイ?": "Ray ―はじまりのセカイ― (クロニクルアレンジver.)",
    "Reach for the Stars": "Reach For The Stars",
    "Re：Re": "Ré：Ré",
    "Session High": "Session High⤴",
    "Seyana": "Seyana. ～何でも言うことを聞いてくれるアカネチャン～",
    "Seyana. ~何でも言うことを聞いてくれるアカネチャン~": "Seyana. ～何でも言うことを聞いてくれるアカネチャン～",
    "Signs Of Love (”Never More” ver.)": "Signs Of Love (“Never More” ver.)",
    "solips": "sølips",
    "Solstand": "Solstånd",
    "Super Lovely": "Super Lovely (Heavenly Remix)",
    "The Metaverse": "The Metaverse -First story of the SeelischTact-",
    "Tuatha De Danann": "Tuatha Dé Danann",
    "Walzer fur das Nichts": "Walzer für das Nichts",
    "Wing No.6223": "Wing:No.6223",
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
    "宵の平安京 Stargaze": "宵の平安京 Stargazer",
    "内臓マニピ": "内臓♡マニピ",
    "ＧＯ！ＧＯ！ラブリズム ～あーりん書類審査通過記念Ver.～": "ＧＯ！ＧＯ！ラブリズム♥ ～あーりん書類審査通過記念Ver.～",
    "《真紅》～ Pavane Pour La Flamme": "《真紅》 ～ Pavane Pour La Flamme",
    "《楽土》～ One and Only One": "《楽土》 ～ One and Only One",
    "《散華》～ EMBARK": "《散華》 ～ EMBARK",
    "《慈雨》～ La Symphonie de Salacia: Agony Movement": "《慈雨》 ～ La Symphonie de Salacia: Agony Movement",
    "《創造》～ Cries, beyond The End": "《創造》 ～ Cries, beyond The End",
    "[隔絶] ～Flame of Determination": "〚隔絶〛 ～Flame of Determination",
    "[献身] ～Paradox of Choice": "〚献身〛 ～Paradox of Choice",
    "[盲従] ～Fantasia Sonata Flower": "〚盲従〛 ～Fantasia Sonata Flower",
    "[空虚] ～Pyrophilia": "〚空虚〛 ～Pyrophilia",
    "美少女無罪パイレーツ": "美少女無罪♡パイレーツ",
    "AMARA (大未来電脳)": "ÅMARA (大未来電脳)",
    "ム責任集合体": "㋰責任集合体",
    "ビッグブリッヂの死闘": "ビッグブリッヂの死闘 -シアトリズムFFAC Arrange- from FFV",
}


async def update_sdvxin(logger: BoundLogger):
    # sdvx.in ID, song_id, difficulty
    with (SEEDS_DIR / "songs.json").open("rb") as f:
        songs = msgspec.json.decode(f.read())

    songs_by_id = {s["id"]: s for s in songs}

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=600)
    ) as client:
        # standard categories
        for category in SDVXIN_CATEGORIES:
            logger.info(f"Processing category {category}")
            if category == "end":
                url = "https://sdvx.in/chunithm/end.htm"
            else:
                url = f"https://sdvx.in/chunithm/sort/{category}.htm"
            resp = await client.get(url)
            soup = LexborHTMLParser(await resp.text(), is_fragment=False)

            tables = soup.css("table:has(td.tbgl)")
            if len(tables) == 0:
                logger.error(f"Could not find table(s) for category {category}")
                continue

            for table in tables:
                scripts = table.css("script[src]")

                for script in scripts:
                    title = None
                    x = script.next

                    while x is not None:
                        if x.is_comment_node:
                            title = x.comment_content
                            break

                        x = x.next

                    if title is None:
                        continue

                    title = TITLE_MAPPING.get(title, unescape(title))
                    sdvx_in_id = str(script.attrs["src"]).split("/")[-1][
                        :5
                    ]  # TODO: dont assume the ID is always 5 digits

                    script_data = None
                    level = None

                    logger.debug(
                        "Finding chart", title=title, level=level, category=category
                    )

                    if category == "end":
                        if sdvx_in_id == "01052":
                            # Invitation WE got revived under a different ID.
                            song = songs_by_id.get(8306)
                        elif sdvx_in_id == "01032":
                            # ナイト・オブ・ナイツ WE got revived under a different ID.
                            song = songs_by_id.get(8309)
                        else:
                            script_resp = await client.get(
                                f"https://sdvx.in{script.attrs['src']}"
                            )
                            script_data = await script_resp.text()

                            if (
                                match := WORLD_END_SDVXIN_REGEX.search(script_data)
                            ) is not None and match.group("difficulty").strip():
                                level = match.group("difficulty").strip()
                            elif (
                                match := WORLD_END_DIFFICULTY_REGEX.search(script_data)
                            ) is not None:
                                kanji = match.group("kanji")
                                star_difficulty = match.group("star_difficulty")
                                level = f"{kanji}{'☆' * int(star_difficulty)}"
                            else:
                                logger.warning(
                                    f"Could not extract difficulty for {title}, {sdvx_in_id}"
                                )
                                continue

                            song = next(
                                (
                                    song
                                    for song in songs
                                    if song["title"] == title
                                    and song["id"] >= 8000
                                    and any(
                                        c["difficulty"] == "WE" and c["level"] == level
                                        for c in song["charts"]
                                    )
                                ),
                                None,
                            )
                    else:
                        song = next(
                            (
                                song
                                for song in songs
                                if song["title"] == title and song["id"] < 8000
                            ),
                            None,
                        )

                    if song is None:
                        if category == "end":
                            logger.warning("Could not find %s [%s]", title, level)
                        else:
                            logger.warning("Could not find %s", title)

                        continue

                    if script_data is None:
                        script_resp = await client.get(
                            f"https://sdvx.in{script.attrs['src']}"
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
                        value_soup = LexborHTMLParser(
                            value.removeprefix('"').removesuffix('";'), is_fragment=True
                        )

                        if value_soup.css_first("a") is None:
                            continue

                        chart = next(
                            (c for c in song["charts"] if c["difficulty"] == level),
                            None,
                        )

                        if chart is not None:
                            chart["sdvxin"] = {"id": sdvx_in_id, "end_index": end_index}
                        else:
                            logger.warning(
                                "Could not find chart",
                                song_id=song["id"],
                                difficulty=level,
                            )

    with (SEEDS_DIR / "songs.json").open("w") as f:
        json.dump(
            songs,
            f,
            cls=SeedsJSONEncoder,
            indent=4,
            ensure_ascii=False,
        )
