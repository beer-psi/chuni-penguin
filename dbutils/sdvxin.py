# ruff: noqa: RUF001

import functools
import itertools
import json
import re

import aiohttp
import msgspec
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
    "AMARA (大未来電脳)": "ÅMARA (大未来電脳)",
    "Aether Crest:Celestial": "Aether Crest: Celestial",
    "AstroNotes.": "AstrøNotes.",
    "Athlete Killer ”Meteor”": 'Athlete Killer "Meteor"',
    "Aventyr": "Äventyr",
    "BOW AND ARROW（アニメ・オープニングver.）": "BOW AND ARROW （アニメ・オープニングver.）",
    "Blooming Villain(ATLUS Konishi Remix)": "Blooming Villain (ATLUS Konishi Remix)",
    "Blow my mind": "Blow My Mind",
    "Change Our MIRAI!": "Change Our MIRAI！",
    "Chaotic Order": "Chaotic Ørder",
    "DAZZLING SEASON": "DAZZLING♡SEASON",
    "DON`T STOP ROCKIN` ~[O_O] MIX~": "D✪N`T ST✪P R✪CKIN` ~[✪_✪] MIX~",
    "DON’T STOP ROCKIN’ ～[O_O] MIX": "D✪N’T ST✪P R✪CKIN’ ～[✪_✪] MIX～",
    "DON’T STOP ROCKIN’ ～[O_O] MIX～": "D✪N’T ST✪P R✪CKIN’ ～[✪_✪] MIX～",
    "Daydream cafe": "Daydream café",
    "Defandour": "Dèfandour",
    "Don't say ”lazy”": 'Don\'t say "lazy"',
    "D✪N'T ST✪P R✪CKIN' ～[✪_✪] MIX～": "D✪N’T ST✪P R✪CKIN’ ～[✪_✪] MIX～",
    "D✪N’T ST✪P R✪CKIN’ ~[✪_✪] MIX~": "D✪N’T ST✪P R✪CKIN’ ～[✪_✪] MIX～",
    "ECHO-": "ECHO",
    "Excalibur": "Excalibur ～Revived resolution～",
    "Excalibur ~Revived resolution~": "Excalibur ～Revived resolution～",
    "GO!GO!ラブリズム ~あーりん書類審査通過記念Ver.~": "GO!GO!ラブリズム♥ ~あーりん書類審査通過記念Ver.~",
    "GRANDIR": "GRÄNDIR",
    "Give me Love?": "Give me Love♡",
    "GranFatalite": "GranFatalité",
    "Help me,あーりん！": "Help me, あーりん！",
    "Help,me あーりん!": "Help me, あーりん!",
    "Help,me あーりん！": "Help me, あーりん！",
    "In The Blue Sky `01": "In The Blue Sky '01",
    "In The Blue Sky ’01": "In The Blue Sky '01",
    "Jorqer": "Jörqer",
    "L'epilogue": "L'épilogue",
    "Little ”Sister” Bitch": 'Little "Sister" Bitch',
    "Love's Theme of BADASS": "Love's Theme of BADASS ～バッド・アス 愛のテーマ～",
    "M@GICAL☆CURE! LOVE SHOT!": "M@GICAL☆CURE! LOVE ♥ SHOT!",
    "Make Up Your World": "Make Up Your World feat. キョンシーのCiちゃん & らっぷびと",
    "Mass Destruction (''P3'' + ''P3F'' ver.)": 'Mass Destruction ("P3" + "P3F" ver.)',
    "Mass Destruction(''P3'' + ''P3F'' ver.)": 'Mass Destruction ("P3" + "P3F" ver.)',
    "MegiddO": "MegiddØ",
    "NYAN-NYA, More! ラブシャイン、Chu?": "NYAN-NYA, More! ラブシャイン、Chu♥",
    "Okeanos": "Ωκεανος",
    "Pump": "Pump!n",
    "Ray ?はじまりのセカイ?": "Ray ―はじまりのセカイ― (クロニクルアレンジver.)",
    "Ray ～はじまりのセカイ～(クロニクルアレンジver.)": "Ray ―はじまりのセカイ― (クロニクルアレンジver.)",
    "Reach for the Stars": "Reach For The Stars",
    "Re：Re": "Ré：Ré",
    "Session High": "Session High⤴",
    "Seyana": "Seyana. ～何でも言うことを聞いてくれるアカネチャン～",
    "Seyana. ~何でも言うことを聞いてくれるアカネチャン~": "Seyana. ～何でも言うことを聞いてくれるアカネチャン～",
    "Signs Of Love (”Never More” ver.)": "Signs Of Love (“Never More” ver.)",
    "Solstand": "Solstånd",
    "Super Lovely": "Super Lovely (Heavenly Remix)",
    "The Metaverse": "The Metaverse -First story of the SeelischTact-",
    "Tuatha De Danann": "Tuatha Dé Danann",
    "Walzer fur das Nichts": "Walzer für das Nichts",
    "Wing No.6223": "Wing:No.6223",
    "Yet Another ''drizzly rain''": "Yet Another ”drizzly rain”",
    "Your Affection\u3000(Daisuke Asakura Remix)": "Your Affection (Daisuke Asakura Remix)",
    "[回帰] ～Scherzo": "〚回帰〛 ～Scherzo ~フォルトゥーナの悪戯~",
    "[献身] ～Paradox of Choice": "〚献身〛 ～Paradox of Choice",
    "[盲従] ～Fantasia Sonata Flower": "〚盲従〛 ～Fantasia Sonata Flower",
    "[空虚] ～Pyrophilia": "〚空虚〛 ～Pyrophilia",
    "[隔絶] ～Flame of Determination": "〚隔絶〛 ～Flame of Determination",
    "chronos": "χρόνος",
    "ouroboros": "ouroboros -twin stroke of the end-",
    "solips": "sølips",
    "”STAR”T": '"STAR"T',
    "≠彡”/了→": '≠彡"/了→',
    "《創造》～ Cries, beyond The End": "《創造》 ～ Cries, beyond The End",
    "《慈雨》 ～ La Symphonie de Salacia:Agony Movement": "《慈雨》 ～ La Symphonie de Salacia: Agony Movement",
    "《慈雨》～ La Symphonie de Salacia: Agony Movement": "《慈雨》 ～ La Symphonie de Salacia: Agony Movement",
    "《散華》～ EMBARK": "《散華》 ～ EMBARK",
    "《楽土》～ One and Only One": "《楽土》 ～ One and Only One",
    "《真紅》～ Pavane Pour La Flamme": "《真紅》 ～ Pavane Pour La Flamme",
    "【3Dサウンド】小夜ちゃんが秘密裏に手に入れたヤベエ機材でヤベエ音を録る話【イヤホン推奨】 (EDテーマ:A.S.S.S.M.R.)": "【3Dサウンド】小夜ちゃんが秘密裏に手に入れたヤベエ機材でヤベエ音を録る話【イヤホン推奨】（EDテーマ：A.S.S.S.M.R.）",
    "【ゆっくり実況】 ゆっくりペンギンが怒槌をやってみた! Part1": "【ゆっくり実況】ゆっくりペンギンが怒槌をやってみた！ Part1",
    "まっすぐ→→→ストリーム!": "まっすぐ→→→ストリーム！",
    "めいど・うぃず・どらごんず": "めいど・うぃず・どらごんず♥",
    "めっちゃ煽ってくる": "めっちゃ煽ってくるタイプの音ゲーボス曲ちゃんなんかに負けないが？？？？？",
    "イロドリミドリ杯 花映塚全一決定戦公式テーマソング『ウソテイ』": "イロドリミドリ杯花映塚全一決定戦公式テーマソング『ウソテイ』",
    "イロドリミドリ杯花映塚全一決定戦 公式テーマソング『ウソテイ』": "イロドリミドリ杯花映塚全一決定戦公式テーマソング『ウソテイ』",
    "キュアリアス光吉古牌\u3000-祭-": "キュアリアス光吉古牌\u3000－祭－",
    "キュアリアス光吉古牌\u3000?祭?": "キュアリアス光吉古牌\u3000－祭－",
    "チルノおかん": "チルノおかんのさいきょう☆バイブスごはん",
    "ナイト・オブ・ナイツ (かめりあ`s“": "ナイト・オブ・ナイツ (かめりあ`s“ワンス・アポン・ア・ナイト”Remix)",
    "ナイト・オブ・ナイツ (かめりあ’s“": "ナイト・オブ・ナイツ (かめりあ’s“ワンス・アポン・ア・ナイト”Remix)",
    "ヒトリシズカ(Arranged:Iceon)": "ヒトリシズカ(Arranged: Iceon)",
    "ビッグブリッヂの死闘": "ビッグブリッヂの死闘 -シアトリズムFFAC Arrange- from FFV",
    "ム責任集合体": "㋰責任集合体",
    "モンダイナイトリッパー": "モンダイナイトリッパー！",
    "ラブって?ジュエリー♪えんじぇる☆ブレイク!!": "ラブって♡ジュエリー♪えんじぇる☆ブレイク!!",
    "ラブって?ジュエリー♪えんじぇる☆ブレイク！！": "ラブって♡ジュエリー♪えんじぇる☆ブレイク！！",
    "ラブって♥ジュエリー♪えんじぇる☆ブレイク！！": "ラブって♡ジュエリー♪えんじぇる☆ブレイク！！",
    "パリピ孔明 CMソング": "パリピ孔明 ＣＭソング",
    "一世嬉遊曲": "一世嬉遊曲‐ディヴェルティメント‐",
    "一世嬉遊曲-ディヴェルティメント-": "一世嬉遊曲‐ディヴェルティメント‐",
    "今ぞ崇め奉れ☆オマエらよ!!~姫の秘メタル渇望~": "今ぞ♡崇め奉れ☆オマエらよ!!~姫の秘メタル渇望~",
    "今ぞ崇め奉れ☆オマエらよ！！～姫の秘メタル渇望～": "今ぞ♡崇め奉れ☆オマエらよ！！～姫の秘メタル渇望～",
    "優勝Princess": "優勝Princess♡",
    "光線チューニング~なずな": "光線チューニング ~なずな妄想海フェスイメージトレーニングVer.~",
    "光線チューニング～なずな": "光線チューニング ～なずな妄想海フェスイメージトレーニングVer.～",
    "内臓マニピ": "内臓♡マニピ",
    "多重未来のカルテット": "多重未来のカルテット -Quartet Theme-",
    "失礼しますが、RIP": "失礼しますが、RIP♡",
    "宵の平安京 Stargaze": "宵の平安京 Stargazer",
    "崩壊歌姫": "崩壊歌姫 -disruptive diva-",
    "愛スクリ～ム！": "愛♡スクリ～ム！",
    "最終鬼畜妹フランドール・S(原口沙輔は鬼畜なのか？remix)": "最終鬼畜妹フランドール・S (原口沙輔は鬼畜なのか？remix)",
    "男装女形表裏一体発狂小娘": "男装女形表裏一体発狂小娘の詐称疑惑と苦悩と情熱。",
    "砂漠のハンティングガール": "砂漠のハンティングガール♡",
    "私の中の幻想的世界観": "私の中の幻想的世界観及びその顕現を想起させたある現実での出来事に関する一考察",
    "美少女無罪パイレーツ": "美少女無罪♡パイレーツ",
    "萌豚功夫大乱舞": "萌豚♥功夫♥大乱舞",
    "ＧＯ！ＧＯ！ラブリズム ～あーりん書類審査通過記念Ver.～": "ＧＯ！ＧＯ！ラブリズム♥ ～あーりん書類審査通過記念Ver.～",
}


class SdvxinSong(msgspec.Struct):
    id: str
    title: str
    artist: str
    levels: dict[str, str] | str
    youtube: dict[str, str]


async def update_sdvxin(logger: BoundLogger):
    # sdvx.in ID, song_id, difficulty
    with (SEEDS_DIR / "songs.json").open("rb") as f:
        songs = msgspec.json.decode(f.read())

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=600)
    ) as client:
        for i in itertools.chain(
            (f"{i:02}" for i in range(1, 21)),
            ["_del", "_we", "_wedel", "_wecourse", "_weuso"],
        ):
            logger.debug("Fetching category", category=f"songs{i}.json")

            resp = await client.get(
                f"https://sdvx.in/chunithm/_/json/songs{i}.json", allow_redirects=False
            )

            if resp.status == 302:
                continue

            sdvxin_songs: list[SdvxinSong] = await resp.json(
                loads=functools.partial(msgspec.json.decode, type=list[SdvxinSong])
            )

            for sdvxin_song in sdvxin_songs:
                title = TITLE_MAPPING.get(sdvxin_song.title, sdvxin_song.title)

                if isinstance(sdvxin_song.levels, str):  # WE entries do this
                    if sdvxin_song.levels.startswith("_"):
                        kanji = sdvxin_song.levels[1]
                        difficulty = sdvxin_song.levels[2]
                    else:
                        kanji = sdvxin_song.levels[0]
                        difficulty = sdvxin_song.levels[1]

                    level = f"{kanji}{'☆' * int(difficulty)}"
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

                    if song is None:
                        logger.warning(
                            "Could not find song",
                            title=sdvxin_song.title,
                            lv=level,
                            levels=sdvxin_song.levels,
                        )
                        continue

                    song["charts"][0]["sdvxin"] = (
                        None
                        if sdvxin_song.levels.startswith("_")
                        else {
                            "id": sdvxin_song.id,
                            "end_index": "",
                        }
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
                        logger.warning("Could not find song", title=sdvxin_song.title)
                        continue

                    charts_by_difficulty = {
                        chart["difficulty"]: chart for chart in song["charts"]
                    }

                    for k, v in sdvxin_song.levels.items():
                        if not v or v.startswith("_"):
                            continue

                        if k == "bsc":
                            difficulty = "BAS"
                        elif k == "mst":
                            difficulty = "MAS"
                        else:
                            difficulty = k.upper()

                        try:
                            charts_by_difficulty[difficulty]["sdvxin"] = {
                                "id": sdvxin_song.id,
                                "end_index": "",
                            }
                        except KeyError:
                            logger.warning(
                                "Could not find chart",
                                title=sdvxin_song.title,
                                difficulty=difficulty,
                            )

    with (SEEDS_DIR / "songs.json").open("w") as f:
        json.dump(
            songs,
            f,
            cls=SeedsJSONEncoder,
            indent=4,
            ensure_ascii=False,
        )
