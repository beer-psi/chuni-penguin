import binascii
import string
from enum import IntEnum, IntFlag, auto
from typing import TYPE_CHECKING, NotRequired, TypedDict, overload

import httpx
from discord import AllowedMentions, Forbidden
from discord.ext import commands
from discord.ext.commands import Context

from chunithm_net.consts import KEY_SONG_ID
from chunithm_net.models.enums import ChainType, ClearType, ComboType, Difficulty

if TYPE_CHECKING:
    from bot import ChuniBot
    from chunithm_net.models.record import Record
    from cogs.botutils import UtilsCog


class ChunirecStatus(TypedDict):
    maintenance: bool
    maintenance_msg: str
    latest_ver_date: int
    provide_rating: bool
    available: bool


class ChunirecGdhttsResponse(TypedDict):
    status: str
    task_id: NotRequired[str]


class ChunirecComboLamp(IntFlag):
    FULL_COMBO = auto()
    ALL_JUSTICE = auto()
    FULL_CHAIN = auto()
    FULL_CHAIN_PLUS = auto()
    ALL_JUSTICE_CRITICAL = auto()


class ChunirecClearLamp(IntEnum):
    FAILED = 0
    CLEAR = auto()
    HARD = auto()
    ABSOLUTE = auto()
    ABSOLUTE_PLUS = auto()
    CATASTROPHY = auto()


class ChunirecCourseLamp(IntFlag):
    CLEAR = auto()
    FULL_COMBO = auto()
    ALL_JUSTICE = auto()
    ALL_JUSTICE_CRITICAL = auto()


BASE62_ALPHABET = string.digits + string.ascii_uppercase + string.ascii_lowercase
TITLE_RARITIES = [
    "x",
    "normal",
    "copper",
    "silver",
    "gold",
    "platina",
    "rainbow",
    "ongeki",
    "staff",
    "maimai",
]


@overload
def to_base_n(number: int, base: int, alphabet: str) -> str: ...


@overload
def to_base_n(number: int, base: int) -> list[int]: ...


def to_base_n(number: int, base: int, alphabet: str | None = None):
    if base < 2:
        msg = "invalid base, must be no less than 2"
        raise ValueError(msg)

    if alphabet is not None and len(alphabet) != base:
        msg = "alphabet cannot fit the given base"
        raise ValueError(msg)

    if number < 0:
        msg = "cannot work with negative numbers"
        raise ValueError(msg)

    if number == 0:
        return alphabet[0] if alphabet else [0]

    digits: list[int] = []

    while number:
        digits.append(number % base)
        number //= base

    digits = digits[::-1]

    if alphabet:
        return "".join([alphabet[x] for x in digits])

    return digits


def clamp(value: int, min: int, max: int):
    if value < min:
        return min
    if value > max:
        return max

    return value


def serialize_number(
    value: int,
    length: int,
    min: int | None = None,
    max: int | None = None,
    alphabet: str = BASE62_ALPHABET,
):
    if min is None:
        min = 0

    if max is None:
        max = 0

        for _ in range(length):
            max *= 62
            max += 61

    return to_base_n(clamp(value, min, max), len(alphabet), alphabet).zfill(length)


def serialize_string(
    value: str,
    length_of_length_field: int,
):
    max_length_of_value = 0

    for _ in range(length_of_length_field):
        max_length_of_value *= 62
        max_length_of_value += 61

    encoded = ""
    ascii_mode = False
    prev_ascii_mode = False

    for c in value:
        prev_ascii_mode = ascii_mode
        ascii_mode = c in BASE62_ALPHABET

        if prev_ascii_mode != ascii_mode:
            encoded += "-"

        if ascii_mode:
            encoded += c
        else:
            encoded += serialize_number(ord(c), 3)

    return (
        serialize_number(min(len(encoded), max_length_of_value), length_of_length_field)
        + encoded[:max_length_of_value]
    )


class ChunirecCog(commands.Cog, name="chunirec", command_attrs={"hidden": True}):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot: ChuniBot = bot
        self.utils: UtilsCog = bot.get_cog("Utils")  # pyright: ignore[reportAttributeAccessIssue]

        self.http_client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=60.0),
            follow_redirects=True,
            transport=httpx.AsyncHTTPTransport(retries=5),
        )
        self.http_client.headers.update(
            {
                "accept-language": "en-US,en;q=0.5",
                "origin": "https://new.chunithm-net.com",
                "referer": "https://new.chunithm-net.com/",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "cross-site",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
            }
        )
        self.region_code = "jp2"

    @commands.hybrid_group("chunirec", invoke_without_command=True)
    async def chunirec(self, ctx: Context):
        await ctx.reply(
            content=(
                "[chunirec](https://chunirec.net) is a score tracker for CHUNITHM Japanese version. It tracks "
                "your personal bests, OVER POWER, rating progression, and more. While the tool doesn't "
                "officially support the International version, this bot can submit your records to be tracked "
                "as if they were Japanese scores."
            ),
            mention_author=False,
        )

    @chunirec.command("sync", aliases=["s"])
    async def chunirec_sync(self, ctx: Context):
        try:
            dm_channel = await ctx.author.create_dm()
        except Forbidden as e:
            msg = "Please open your DMs to sync scores to chunirec."
            raise commands.PrivateMessageOnly(msg) from e

        resp = await self.http_client.get(
            f"https://api.chunirec.net/2.0/pttgr/status.json?region={self.region_code}"
        )
        status: ChunirecStatus = resp.json()

        if not status["available"]:
            msg = "chunirec is currently not available. Please try again later."
            raise commands.CommandError(msg)

        if status["maintenance"]:
            msg = f"chunirec is down for maintenance: {status['maintenance_msg']}"
            raise commands.CommandError(msg)

        message = await ctx.reply("Fetching player data...", mention_author=False)
        payload = "06"

        async with self.utils.chuninet(ctx) as client:
            player_data = await client.player_data()

            payload += serialize_number(player_data.lv, 3, max=9999)
            payload += serialize_number(
                int(player_data.rating.current * 100), 3, max=9999
            )
            payload += serialize_number(
                int(player_data.rating.max * 100) if player_data.rating.max else 0,
                3,
                max=9999,
            )
            payload += serialize_number(player_data.playcount or 0, 4)

            class_emblem = 0

            if player_data.medal is not None:
                class_emblem += player_data.medal.value
            if player_data.emblem is not None:
                class_emblem += player_data.emblem.value * 7

            payload += serialize_number(class_emblem, 1, max=48)
            payload += serialize_number(1 if player_data.team is not None else 0, 1)

            try:
                title_rarity = TITLE_RARITIES.index(player_data.nameplate.rarity)
            except ValueError:
                title_rarity = 0

            payload += "1"  # number of titles set, hardcoded to 1 until VERSE is released in intl
            payload += serialize_number(title_rarity, 1, max=9)
            payload += "0"  # seemingly deprecated field
            payload += "3"  # region index: paralost = 1, intl = 2, jp = 3
            payload += "0"  # net battle rank
            payload += "000"  # net battle playcount
            payload += serialize_string(player_data.name, 2)

            # for verse, just serialize all 3 titles
            payload += serialize_string(player_data.nameplate.content, 2)

            records: list[Record] = []

            for difficulty in Difficulty:
                await message.edit(
                    content=f"Fetching {difficulty} scores...",
                    allowed_mentions=AllowedMentions.none(),
                )

                records.extend(
                    await client.music_record_by_folder(difficulty=difficulty)
                )

            payload += serialize_number(len(records), 3)
            payload += "S"  # marker for PB array

            for record in records:
                payload += serialize_number(
                    record.extras[KEY_SONG_ID] % 20480
                    + record.difficulty.value * 20480,
                    3,
                )
                payload += serialize_number(record.score, 4, max=1_010_000)

                combo_lamp: ChunirecComboLamp = ChunirecComboLamp(0)

                if record.combo_lamp == ComboType.ALL_JUSTICE_CRITICAL:
                    combo_lamp |= ChunirecComboLamp.ALL_JUSTICE_CRITICAL
                elif record.combo_lamp == ComboType.ALL_JUSTICE:
                    combo_lamp |= ChunirecComboLamp.ALL_JUSTICE
                elif record.combo_lamp == ComboType.FULL_COMBO:
                    combo_lamp |= ChunirecComboLamp.FULL_COMBO

                if record.chain_lamp == ChainType.FULL_CHAIN_PLUS:
                    combo_lamp |= ChunirecComboLamp.FULL_CHAIN_PLUS
                elif record.chain_lamp == ChainType.FULL_CHAIN:
                    combo_lamp |= ChunirecComboLamp.FULL_CHAIN

                clear_lamp = ChunirecClearLamp.FAILED

                if record.clear_lamp == ClearType.CLEAR:
                    clear_lamp = ChunirecClearLamp.CLEAR
                elif record.clear_lamp == ClearType.HARD:
                    clear_lamp = ChunirecClearLamp.HARD
                elif record.clear_lamp == ClearType.ABSOLUTE:
                    clear_lamp = ChunirecClearLamp.ABSOLUTE
                elif record.clear_lamp == ClearType.ABSOLUTE_PLUS:
                    clear_lamp = ChunirecClearLamp.ABSOLUTE_PLUS
                elif record.clear_lamp == ClearType.CATASTROPHY:
                    clear_lamp = ChunirecClearLamp.CATASTROPHY

                payload += serialize_number(combo_lamp.value, 1, max=31)
                payload += serialize_number(clear_lamp.value, 1, max=31)

            await message.edit(
                content="Fetching courses...",
                allowed_mentions=AllowedMentions.none(),
            )
            courses = await client.course_record()

            payload += serialize_number(len(courses), 3)
            payload += "C"  # marker for course array

            for course in courses:
                payload += serialize_number(course.id, 3)
                payload += serialize_number(course.score, 4, max=3_030_000)

                course_lamp = ChunirecCourseLamp(0)

                if course.clear_lamp == ClearType.CLEAR:
                    course_lamp |= ChunirecCourseLamp.CLEAR

                if course.combo_lamp in (
                    ComboType.ALL_JUSTICE_CRITICAL,
                    ComboType.ALL_JUSTICE,
                ):
                    course_lamp |= ChunirecCourseLamp.ALL_JUSTICE
                elif course.combo_lamp == ComboType.FULL_COMBO:
                    course_lamp |= ChunirecCourseLamp.FULL_COMBO

                payload += serialize_number(course_lamp.value, 1, max=7)

            await message.edit(
                content="Fetching recent10...",
                allowed_mentions=AllowedMentions.none(),
            )
            recent10 = await client.recent10()

            payload += serialize_number(len(recent10), 3)
            payload += "R"  # marker for course array

            for recent in recent10:
                payload += serialize_number(
                    recent.extras[KEY_SONG_ID] % 20480
                    + recent.difficulty.value * 20480,
                    3,
                )
                payload += serialize_number(recent.score, 4, max=1_010_000)

            payload += "000B"  # unused array, presumably for best30
            payload += "000O"  # unused array, presumably for best40

            payload += serialize_number(binascii.crc32(payload.encode()), 6)

        resp = await self.http_client.post(
            "https://api.chunirec.net/2.0/pttgr/gdhtts.json",
            data={"data": payload},
        )
        data: ChunirecGdhttsResponse = resp.json()

        if data["status"] != "ok":
            await message.delete()

            msg = f"Could not submit scores to chunirec: {data['status']}"
            raise commands.CommandError(msg)

        assert "task_id" in data

        await message.edit(
            content="Import complete. Please check in your DMs for a URL to save records to your chunirec account.",
            allowed_mentions=AllowedMentions.none(),
        )
        await dm_channel.send(
            content=f"Click this link to save records to your chunirec account: https://chunirec.net/api/pttgr/resend?task_id={data['task_id']}"
        )


async def setup(bot: "ChuniBot"):
    await bot.add_cog(ChunirecCog(bot))
