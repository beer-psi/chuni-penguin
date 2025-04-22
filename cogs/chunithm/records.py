import asyncio
import contextlib
import itertools
import urllib.parse
from argparse import ArgumentError
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Optional, cast

import discord
import httpx
import msgspec
from discord import AllowedMentions, Interaction, app_commands
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import escape_markdown
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from chunithm_net.consts import (
    INTERNATIONAL_JACKET_BASE,
    JACKET_BASE,
    KEY_INTERNAL_LEVEL,
    KEY_LEVEL,
    KEY_OVERPOWER_BASE,
    KEY_OVERPOWER_MAX,
    KEY_PLAY_RATING,
    KEY_SONG_GENRE,
    KEY_SONG_ID,
)
from chunithm_net.models.enums import ComboType, Difficulty, Genres, Rank
from chunithm_net.models.record import (
    DetailedRecentRecord,
    RecentRecord,
    Record,
)
from database.models import Chart, SongJacket, UserConfig
from utils import did_you_mean_text, floor_to_ndp, json_loads, shlex_split
from utils.argparse import DiscordArguments
from utils.components import ScoreCardEmbed
from utils.config import config
from utils.constants import CURRENT_CHUNITHM_VERSION_KT, SIMILARITY_THRESHOLD
from utils.converters import (
    AliasNameConverter,
    AliasNameTransformer,
    DifficultyConverter,
    GenreConverter,
    RankConverter,
)
from utils.kamaitachi import (
    KTChunithmPersonalBestResponseBody,
    convert_kt_pbs_to_records,
    convert_kt_scores_to_records,
    convert_kt_to_record,
)
from utils.logging import logged_app_command, logged_prefix_command
from utils.views import (
    B30N20View,
    B30View,
    RecentRecordsView,
    SelectToCompareView,
)
from utils.views.embeds import EmbedPaginationView
from utils.views.leaderboard import LeaderboardView

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.autocompleters import AutocompletersCog
    from cogs.botutils import UtilsCog


ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
NOTO_SANS_JP_24 = ImageFont.truetype(
    ASSETS_DIR / "fonts" / "NotoSansJP-Regular.ttf", 24
)
NOTO_SANS_JP_24_BOLD = ImageFont.truetype(
    ASSETS_DIR / "fonts" / "NotoSansJP-Bold.ttf", 24
)
NOTO_SANS_JP_28_MEDIUM = ImageFont.truetype(
    ASSETS_DIR / "fonts" / "NotoSansJP-Medium.ttf", 28
)
NOTO_SANS_JP_32_BOLD = ImageFont.truetype(
    ASSETS_DIR / "fonts" / "NotoSansJP-Bold.ttf", 32
)
NOTO_SANS_JP_40_BOLD = ImageFont.truetype(
    ASSETS_DIR / "fonts" / "NotoSansJP-Bold.ttf", 40
)
NOTO_SANS_JP_64_BOLD = ImageFont.truetype(
    ASSETS_DIR / "fonts" / "NotoSansJP-Bold.ttf", 64
)
INTER_32 = ImageFont.truetype(ASSETS_DIR / "fonts" / "Inter_28pt-Regular.ttf", 32)
INTER_40_BOLD = ImageFont.truetype(ASSETS_DIR / "fonts" / "Inter_28pt-Bold.ttf", 40)
INTER_44_BOLD = ImageFont.truetype(ASSETS_DIR / "fonts" / "Inter_28pt-Bold.ttf", 44)

B30_HEADER_HEIGHT = 220
B30_HEADER_SPACING = 185
B30_OLD_NEW_SPACING = 130
B30_FOOTER_SPACING = 95
B30_FOOTER_HEIGHT = 70
B30_ENTRY_WIDTH = 350
B30_ENTRY_HEIGHT = 215
B30_ENTRY_WIDTH_SPACING = 15
B30_ENTRY_HEIGHT_SPACING = 25
B30_JACKET_WIDTH = 110
B30_JACKET_HEIGHT = 110
INVITE_LINK = "https://chunithm.beerpsi.cc/invite"


class reversor:
    def __init__(self, obj):
        self.obj = obj

    def __eq__(self, other):
        return other.obj == self.obj

    def __lt__(self, other):
        return other.obj < self.obj


def _render_b30_entry(
    b30_image: Image.Image,
    record: Record,
    i: int,
    x: int,
    y: int,
    user_config: UserConfig | None = None,
):
    # get the jacket
    song_id = record.extras[KEY_SONG_ID]
    jacket_basename = f"{song_id}"

    if song_id == 2698 and user_config is not None:
        if user_config.synthesis_alt_jacket == "cytus2":
            jacket_basename = "2698_cytus2"
        elif user_config.synthesis_alt_jacket == "vividstasis":
            jacket_basename = "2698_vividstasis"
        elif user_config.synthesis_alt_jacket == "musedash":
            jacket_basename = "2698_musedash"
        elif user_config.synthesis_alt_jacket == "none":
            jacket_basename = "__nonexistent"

    jacket_path = ASSETS_DIR / "jackets" / f"{jacket_basename}.png"
    prerendered_path = (
        ASSETS_DIR / "jackets" / f"{jacket_basename}_{record.difficulty.value}.png"
    )

    if prerendered_path.exists():
        with Image.open(prerendered_path) as prerendered:
            b30_image.paste(prerendered, (x, y), prerendered)
    else:
        # draw the base image based on the difficulty
        b30_base_image_path = (
            ASSETS_DIR / "b50" / f"b50_base_{record.difficulty.value}.png"
        )

        with Image.open(b30_base_image_path) as b30_base_image:
            b30_image.paste(b30_base_image, (x, y), b30_base_image)

        # we use try/catch on jacket processing to gracefully fail to a black image
        # if the jacket is missing or corrupted
        try:
            with Image.open(jacket_path) as jacket:
                # convert the jacket to RGB since ImageEnhance explodes in different modes
                # resize the jacket
                jacket = jacket.convert("RGB").resize(
                    (B30_JACKET_WIDTH, B30_JACKET_HEIGHT)
                )

        except (FileNotFoundError, ValueError):
            # fallback to a black background if anything fails
            jacket = Image.new("RGB", (B30_JACKET_WIDTH, B30_JACKET_HEIGHT), 0)

        # draw the jacket art onto the card
        b30_image.paste(jacket, (x + 10, y + 60))

    b30_draw = ImageDraw.Draw(b30_image)

    # if the title doesn't fit the b30 entry rectangle, shorten it until it fits.
    title = record.title
    title_length = b30_draw.textlength(title, NOTO_SANS_JP_32_BOLD)

    while title_length > B30_ENTRY_WIDTH - 25:
        title = title[:-1]
        title_length = b30_draw.textlength(title + "...", NOTO_SANS_JP_32_BOLD)

    # draw the title
    b30_draw.text(
        (x + 10, y),
        title + ("..." if title != record.title else ""),
        fill="#FFFFFF",
        font=NOTO_SANS_JP_32_BOLD,
    )

    # draw the score
    b30_draw.text(
        (x + 132, y + 50),
        f"{record.score:,}",
        fill="#FFFFFF",
        font=NOTO_SANS_JP_32_BOLD,
    )

    # draw the lamps
    rank_lamp = f"[{record.rank}]"
    b30_draw.text(
        (x + 132, y + 90),
        rank_lamp,
        fill="#DDDDDD",
        font=NOTO_SANS_JP_24,
    )

    if record.combo_lamp != ComboType.NONE:
        rank_lamp_width = b30_draw.textlength(rank_lamp + " ", NOTO_SANS_JP_24)

        if record.combo_lamp == ComboType.ALL_JUSTICE_CRITICAL:
            combo_lamp = "[AJC]"
            combo_lamp_color = "#FFDF75"
        elif record.combo_lamp == ComboType.ALL_JUSTICE:
            combo_lamp = "[AJ]"
            combo_lamp_color = "#FFDF75"
        elif record.combo_lamp == ComboType.FULL_COMBO:
            combo_lamp = "[FC]"
            combo_lamp_color = "#28F31A"
        else:
            msg = f"unhandled combo lamp {record.combo_lamp}"
            raise ValueError(msg)

        b30_draw.text(
            (x + 132 + rank_lamp_width, y + 90),
            combo_lamp,
            fill=combo_lamp_color,
            font=NOTO_SANS_JP_24_BOLD,
        )

    # draw the timestamp and judgements if available
    extra_info = ""

    if isinstance(record, RecentRecord) and record.date.timestamp() > 0:
        difference = datetime.now(UTC) - record.date

        if difference.days >= 365:
            delta = f"{difference.days // 365}y"
        elif difference.days >= 30:
            delta = f"{difference.days // 30}mo"
        elif difference.days >= 1:
            delta = f"{difference.days}d"
        elif difference.seconds >= 3600:
            delta = f"{difference.seconds // 3600}h"
        elif difference.seconds >= 60:
            delta = f"{difference.seconds // 60}m"
        elif difference.seconds >= 1:
            delta = f"{difference.seconds}s"
        else:
            delta = "0s"

        extra_info = delta

    if isinstance(record, DetailedRecentRecord):
        if extra_info != "":
            extra_info += f" | {record.judgements.jcrit} – {record.judgements.justice} – {record.judgements.attack} – {record.judgements.miss}"  # noqa: RUF001
        else:
            extra_info += f"{record.judgements.jcrit} – {record.judgements.justice} – {record.judgements.attack} – {record.judgements.miss}"  # noqa: RUF001

    b30_draw.text(
        (x + 10, y + 176),
        extra_info,
        fill="#BBBBBB",
        font=NOTO_SANS_JP_24,
    )

    # draw the rank of the b30 entry
    rank_text_length = b30_draw.textlength(f"#{i + 1}", NOTO_SANS_JP_28_MEDIUM)
    b30_draw.text(
        (x + B30_ENTRY_WIDTH - 10 - rank_text_length, y + 174),
        f"#{i + 1}",
        fill="#FFFFFF",
        font=NOTO_SANS_JP_28_MEDIUM,
    )

    # draw the internal level
    b30_draw.text(
        (x + 132, y + 128),
        f"{record.extras.get(KEY_INTERNAL_LEVEL):.1f}",
        fill="#FFFFFF",
        font=NOTO_SANS_JP_28_MEDIUM,
    )

    # draw the rating value
    rating_text_length = b30_draw.textlength(
        f"{record.extras.get(KEY_PLAY_RATING):.2f}", NOTO_SANS_JP_40_BOLD
    )
    rating_value_color = "#FFFFFF"
    if record.score >= 1_009_000:
        rating_value_color = "#FAFFA5"
    b30_draw.text(
        (x + B30_ENTRY_WIDTH - 10 - rating_text_length, y + 118),
        f"{record.extras.get(KEY_PLAY_RATING):.2f}",
        fill=rating_value_color,
        font=NOTO_SANS_JP_40_BOLD,
    )

    return b30_image


def render_b30(
    player_name: str,
    records: list[Record],
    record_slots: int = 30,
    new_records: list[Record] | None = None,
    new_record_slots: int = 20,
    current_rating: float | None = None,
    user_config: UserConfig | None = None,
):
    if len(records) > record_slots:
        msg = "More records provided than number of record slots"
        raise ValueError(msg)

    if new_records is not None and len(new_records) > new_record_slots:
        msg = "More new records provided than number of new record slots"
        raise ValueError(msg)

    row_num = ceil(record_slots / 5)

    # calculate image height
    image_height = (
        B30_HEADER_HEIGHT
        + B30_HEADER_SPACING
        + (B30_ENTRY_HEIGHT + B30_ENTRY_HEIGHT_SPACING) * row_num
        + B30_FOOTER_SPACING
        + B30_FOOTER_HEIGHT
    )

    # Add a gap between old rating and new rating, if it is provided
    if new_records is not None:
        new_row_num = ceil(new_record_slots / 5)
        image_height += B30_OLD_NEW_SPACING + (B30_ENTRY_HEIGHT + 15) * new_row_num

    b30_image = Image.new("RGBA", size=(1872, image_height), color="#FFFFFF")

    # draw background
    with Image.open(ASSETS_DIR / "b50" / "b50_bg.png") as im:
        im = im.resize((im.width * b30_image.height // im.height, b30_image.height))
        im = im.crop(
            (
                (im.width - b30_image.width) / 2,
                (im.height - b30_image.height) / 2,
                (im.width + b30_image.width) / 2,
                (im.height + b30_image.height) / 2,
            )
        )
        b30_image.paste(im.filter(ImageFilter.GaussianBlur(5)))

    # draw background overlay
    with Image.open(ASSETS_DIR / "b50" / "b50_overlay.png") as im:
        im = im.resize((im.width * b30_image.height // im.height, b30_image.height))
        im = im.crop(
            (
                (im.width - b30_image.width) / 2,
                (im.height - b30_image.height) / 2,
                (im.width + b30_image.width) / 2,
                (im.height + b30_image.height) / 2,
            )
        )
        b30_image = Image.alpha_composite(
            b30_image, im.filter(ImageFilter.GaussianBlur(5))
        )

    # draw header overlay
    with Image.open(ASSETS_DIR / "b50" / "b50_part_header.png") as im:
        header_padded = Image.new("RGBA", b30_image.size)
        header_padded.paste(im, (0, 0))
        b30_image = Image.alpha_composite(b30_image, header_padded)

    # draw logo
    with Image.open(ASSETS_DIR / "b50" / "b50_logo.png") as im:
        logo_padded = Image.new("RGBA", b30_image.size)
        logo_padded.paste(im, (1442, 10))
        b30_image = Image.alpha_composite(b30_image, logo_padded)

    # draw generated date overlay
    with Image.open(ASSETS_DIR / "b50" / "b50_part_date.png") as im:
        date_padded = Image.new("RGBA", b30_image.size)
        date_padded.paste(im, (1492, 310))
        b30_image = Image.alpha_composite(b30_image, date_padded)

    # draw semitransparent rectangles to darken footer
    b30_semitransparent_base = Image.new("RGBA", b30_image.size)
    b30_semitransparent_draw = ImageDraw.Draw(b30_semitransparent_base)
    # draw footer separation line
    b30_semitransparent_draw.rectangle(
        (
            0,
            b30_image.height - B30_FOOTER_HEIGHT - 2,
            b30_image.width,
            b30_image.height - B30_FOOTER_HEIGHT,
        ),
        fill=(0, 0, 0, 200),
    )
    # darken footer
    b30_semitransparent_draw.rectangle(
        (0, b30_image.height - B30_FOOTER_HEIGHT, b30_image.width, b30_image.height),
        fill=(0, 0, 0, 120),
    )
    # paste the darkened parts onto the image
    b30_image = Image.alpha_composite(b30_image, b30_semitransparent_base)

    b30_draw = ImageDraw.Draw(b30_image)

    # draw player name
    player_name_length = b30_draw.textlength(player_name, NOTO_SANS_JP_64_BOLD)
    b30_draw.text(
        (390 - player_name_length / 2, 64),
        player_name,
        fill="#FFFFFF",
        font=NOTO_SANS_JP_64_BOLD,
    )

    # get rating values
    total_rating = sum(
        (item.extras[KEY_PLAY_RATING] for item in records), start=Decimal(0)
    )
    average = floor_to_ndp(total_rating / record_slots, 4)
    new_average = 0

    # draw the rating information
    if new_records is None:
        rating_title = "NAIVE RATING"
        raw_rating_text = f"({average:.4f})"
        final_rating = floor_to_ndp(average, 2)
    else:
        rating_title = "RATING"
        new_total_rating = sum(
            (item.extras[KEY_PLAY_RATING] for item in new_records), start=Decimal(0)
        )
        new_average = floor_to_ndp(
            new_total_rating / new_record_slots,
            4,
        )
        overall_average = floor_to_ndp(
            (total_rating + new_total_rating) / (record_slots + new_record_slots), 4
        )
        raw_rating_text = f"({overall_average:.4f})"
        final_rating = floor_to_ndp(overall_average, 2)

    # draw the text "RATING"
    b30_draw.text(
        (790, 22),
        rating_title,
        fill="#DDDDDD",
        font=INTER_32,
    )

    if current_rating is not None:
        final_rating = current_rating

    rating_text = f"{final_rating:.2f}"

    # set rating color
    rating_thresholds = [
        (17.00, 10),
        (16.00, 9),
        (15.25, 8),
        (14.50, 7),
        (13.25, 6),
        (12.00, 5),
        (10.00, 4),
        (7.00, 3),
        (4.00, 2),
    ]

    rating_tier = 1
    for threshold, tier in rating_thresholds:
        if final_rating >= threshold:
            rating_tier = tier
            break

    # draw the rating number
    digit_x = 810
    digit_count = 0
    if final_rating < 10:
        digit_x = 835
        digit_count = 1

    for char in rating_text:
        # draw each digit of the rating number
        digit_count += 1
        image_name = (
            f"rating_{rating_tier}_{char}.png"
            if char != "."
            else f"rating_{rating_tier}_dot.png"
        )
        digit_path = ASSETS_DIR / "b50" / image_name

        with Image.open(digit_path).convert("RGBA") as digit_im:
            digit_padded = Image.new("RGBA", b30_image.size)
            digit_padded.paste(digit_im, (digit_x, 58))
            b30_image = Image.alpha_composite(b30_image, digit_padded)

        digit_x += 40
        if digit_count == 1 or digit_count == 4:
            digit_x += 10

    b30_draw = ImageDraw.Draw(b30_image)

    # determine the size of raw rating text to properly right-align it
    raw_rating_text_length = b30_draw.textlength(raw_rating_text, INTER_32)

    # draw the raw rating
    b30_draw.text(
        (1090 - raw_rating_text_length, 162),
        raw_rating_text,
        fill="#DDDDDD",
        font=INTER_32,
    )

    # determine the size of the timestamp to properly right-align it
    updated_text = f"{datetime.now(UTC).strftime('%Y-%m-%d')}"
    updated_length = b30_draw.textlength(updated_text, INTER_40_BOLD)

    # draw the timestamp
    b30_draw.text(
        (
            b30_image.width - updated_length - 40,
            318,
        ),
        updated_text,
        fill="#DDDDDD",
        font=INTER_40_BOLD,
    )

    # draw the credits
    b30_draw.text(
        (30, b30_image.height - 57),
        "Generated by chuni penguin#3127",
        fill="#DDDDDD",
        font=INTER_32,
    )

    # determine the size of invite link to properly right-align it
    invite_link_text_length = b30_draw.textlength(INVITE_LINK, INTER_32)

    # draw the invite link
    b30_draw.text(
        (b30_image.width - 30 - invite_link_text_length, b30_image.height - 57),
        INVITE_LINK,
        fill="#DDDDDD",
        font=INTER_32,
    )

    # best30
    for i, record in enumerate(records):
        # top left corner of each b30 entry
        # - the initial 30 is left margin
        # - the (i % 5) and (i // 5) are the b30's position on the grid, so this goes
        # left to right, top to bottom
        x = 30 + (i % 5) * (B30_ENTRY_WIDTH + B30_ENTRY_WIDTH_SPACING)
        y = (
            B30_HEADER_HEIGHT
            + B30_HEADER_SPACING
            + (i // 5) * (B30_ENTRY_HEIGHT + B30_ENTRY_HEIGHT_SPACING)
        )

        b30_image = _render_b30_entry(b30_image, record, i, x, y, user_config)

    if new_records is not None:
        # draw the "OLD CHARTS" and "NEW CHARTS" separators
        with Image.open(ASSETS_DIR / "b50" / "b50_part_old.png") as im:
            old_padded = Image.new("RGBA", b30_image.size)
            old_padded.paste(im, (0, 300))
            b30_image = Image.alpha_composite(b30_image, old_padded)

        with Image.open(ASSETS_DIR / "b50" / "b50_part_new.png") as im:
            new_padded = Image.new("RGBA", b30_image.size)
            new_padded.paste(im, (0, 1870))
            b30_image = Image.alpha_composite(b30_image, new_padded)

        b30_draw = ImageDraw.Draw(b30_image)

        # draw b30 average
        b30_draw.text(
            (40, 316),
            "OLD CHARTS",
            fill="#FFFFFF",
            font=INTER_40_BOLD,
        )
        b30_draw.text(
            (420, 314),
            f"{average:.4f}",
            fill="#000000",
            font=INTER_44_BOLD,
        )

        # draw n20 average
        b30_draw.text(
            (40, 1886),
            "NEW CHARTS",
            fill="#FFFFFF",
            font=INTER_40_BOLD,
        )
        b30_draw.text(
            (420, 1884),
            f"{new_average:.4f}",
            fill="#000000",
            font=INTER_44_BOLD,
        )

        for i, record in enumerate(new_records):
            x = 30 + (i % 5) * (B30_ENTRY_WIDTH + B30_ENTRY_WIDTH_SPACING)

            y = (
                B30_HEADER_HEIGHT
                + B30_HEADER_SPACING
                + 6 * (B30_ENTRY_HEIGHT + B30_ENTRY_HEIGHT_SPACING)
                + B30_OLD_NEW_SPACING
                + (i // 5) * (B30_ENTRY_HEIGHT + B30_ENTRY_HEIGHT_SPACING)
            )

            b30_image = _render_b30_entry(b30_image, record, i, x, y, user_config)

    # crop any extra bits we don't need, however we might need them later...
    # b30_image = b30_image.crop((0, 0, b30_image.width, 1429))

    buffer = BytesIO()

    b30_image.save(buffer, "PNG", compress_level=3)
    buffer.seek(0)

    return buffer


class RecordsCog(commands.Cog, name="Records"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = self.bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]
        self.autocompleters: "AutocompletersCog" = self.bot.get_cog("Autocompleters")  # type: ignore[reportGeneralTypeIssues]

    async def _recent_inner(
        self,
        ctx: Context,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id

        kamaitachi = (
            await self.utils.choose_preferred_network(
                ctx, target_id, kamaitachi=kamaitachi
            )
            == "kamaitachi"
        )

        async with ctx.typing():
            if kamaitachi:
                async with self.utils.kamaitachi_client(ctx, target_id) as client:
                    resp = await client.get("https://kamai.tachi.ac/api/v1/users/me")
                    data = json_loads(resp.content)

                    if not data["success"]:
                        msg = f"Could not get user information from Kamaitachi: {data['success']}"
                        raise commands.CommandError(msg)

                    username = data["body"]["username"]

                    resp = await client.get(
                        "https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single/scores/recent"
                    )
                    data = json_loads(resp.content)

                    if not data["success"]:
                        msg = f"Could not retrieve recent scores from Kamaitachi: {data['description']}"
                        raise commands.CommandError(msg)

                    recents = convert_kt_scores_to_records(data["body"])
                    recents = await self.utils.hydrate_records(recents)

                    view = B30View(
                        ctx,
                        recents,
                        show_average=False,
                        show_reachable=False,
                        show_lamps=True,
                    )
                    await view.start(
                        content=f"Most recent scores for {username} on Kamaitachi:"
                    )
                    return

            ctxmgr = self.utils.chuninet(ctx, target_id)
            client = await ctxmgr.__aenter__()
            userinfo = await client.authenticate()
            recents = await client.recent_record()

            if len(recents) == 0:
                await ctx.reply(
                    f"No recent scores found for {userinfo.name}.", mention_author=False
                )
                return

            hydrated_recents = await self.utils.hydrate_records(recents)

            view = RecentRecordsView(
                ctx, self.bot, hydrated_recents, client, ctxmgr, userinfo
            )
            await view.start(
                content=f"Most recent credits for {userinfo.name}:",
            )

    @commands.command(name="recent", aliases=["rs"])
    @logged_prefix_command
    async def recent(self, ctx: Context, *, query: str = ""):
        """View your recent scores.

        **Parameters**:
        `user`: The user to get scores for.
        `-k, --kamaitachi`: Get recent scores from Kamaitachi, if the user has that linked.
        """

        parser = DiscordArguments()
        parser.add_argument("-k", "--kamaitachi", action="store_true")

        try:
            args, rest = await parser.parse_known_intermixed_args(shlex_split(query))
        except ArgumentError as e:
            raise commands.BadArgument(str(e)) from e

        user = None

        if len(rest) > 0:
            for converter in [commands.MemberConverter, commands.UserConverter]:
                with contextlib.suppress(commands.BadArgument):
                    user = await converter().convert(ctx, rest[0])
                    break

        await self._recent_inner(ctx, user, kamaitachi=args.kamaitachi)

    @app_commands.command(name="recent", description="View recent scores")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        user="The user to get recent scores for",
        kamaitachi="Get recent scores from Kamaitachi, if linked",
    )
    @logged_app_command
    async def recent_slash(
        self,
        interaction: Interaction,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        ctx = await Context.from_interaction(interaction)

        return await self._recent_inner(ctx, user, kamaitachi=kamaitachi)

    async def _compare_inner(
        self,
        ctx: Context,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id

        kamaitachi = (
            await self.utils.choose_preferred_network(
                ctx, target_id, kamaitachi=kamaitachi
            )
            == "kamaitachi"
        )

        url_whitelist = [JACKET_BASE, INTERNATIONAL_JACKET_BASE]
        check_served_jackets = False

        if config.web.serve_assets and config.web.base_url is not None:
            url = httpx.URL(config.web.base_url)

            if not url.host.startswith("127.") and url.host != "localhost":
                url_whitelist.append(f"{config.web.base_url}/assets/jackets/")
                check_served_jackets = True

        async with ctx.typing(), self.bot.begin_db_session() as session:
            message: discord.Message | discord.MessageSnapshot

            if ctx.message.reference is not None:
                message = await ctx.channel.fetch_message(
                    cast(int, ctx.message.reference.message_id)
                )
            else:
                try:

                    def check(m: discord.Message):
                        nonlocal url_whitelist

                        if m.author != self.bot.user:
                            return False

                        embeds = m.embeds.copy()

                        for snapshot in m.message_snapshots:
                            embeds.extend(snapshot.embeds)

                        return any(
                            e.thumbnail.url is not None
                            and any(url in e.thumbnail.url for url in url_whitelist)
                            for e in embeds
                        )

                    messages = [
                        x async for x in ctx.channel.history(limit=50) if check(x)
                    ]
                except discord.errors.Forbidden as e:
                    msg = "Bot requires the Read Message History permission to fetch recent scores."

                    if ctx.interaction is None:
                        msg += f" Alternatively, run `{ctx.prefix}compare` while replying to the score you want to compare."

                    raise commands.CheckFailure(msg) from e

                if len(messages) == 0:
                    msg = "No recent scores found."
                    raise commands.CommandError(msg)

                message = messages[0]

            thumbnail_urls = []
            embeds = message.embeds.copy()

            for snapshot in message.message_snapshots:
                embeds.extend(snapshot.embeds)

            for e in embeds:
                if e.thumbnail.url is not None:
                    thumbnail_urls.append(e.thumbnail.url)
                elif e.image.url is not None:
                    thumbnail_urls.append(e.image.url)

            if len(thumbnail_urls) == 0:
                msg = "The message replied to does not contain any charts/scores."
                raise commands.BadArgument(msg)

            condition = SongJacket.jacket_url.in_(thumbnail_urls)

            if check_served_jackets:
                ids = [
                    int(x.split("/")[-1].split(".")[0])
                    for x in thumbnail_urls
                    if f"{config.web.base_url}/assets/jackets/" in x
                ]
                condition |= SongJacket.song_id.in_(ids)

            sql = (
                select(SongJacket)
                .where(condition)
                .group_by(SongJacket.song_id)
                .options(joinedload(SongJacket.song))
            )
            jackets = (await session.execute(sql)).scalars().all()

            if len(jackets) == 0:
                msg = "No songs found."
                raise commands.CommandError(msg)

            if len(jackets) > 1:
                view = SelectToCompareView(
                    [(x.song.title, i) for i, x in enumerate(jackets)]
                )
                compare_message = await ctx.reply(
                    "Select a score to compare with:", view=view, mention_author=False
                )

                await view.wait()

                if view.value is None:
                    await compare_message.edit(
                        content="Timed out before selecting a score.",
                        view=None,
                        allowed_mentions=AllowedMentions.none(),
                    )
                    return

                jacket = jackets[int(view.value)]
                song = jacket.song
            else:
                compare_message = None
                jacket = jackets[0]
                song = jacket.song

            if not kamaitachi:
                song.raise_if_not_available()

            embed = next(
                x
                for x in embeds
                if (jacket.jacket_url in {x.thumbnail.url, x.image.url})
                or (
                    check_served_jackets
                    and f"{config.web.base_url}/assets/jackets/{jacket.song_id}.png"
                    in {x.thumbnail.url, x.image.url}
                )
            )

            if kamaitachi:
                if song.genre == "WORLD'S END":
                    embed = discord.Embed(
                        title="Error",
                        description="Kamaitachi does not support WORLD'S END charts.",
                        color=discord.Color.red(),
                    )

                    if compare_message is not None:
                        await compare_message.edit(
                            content=None,
                            embed=embed,
                            allowed_mentions=AllowedMentions.none(),
                        )
                        return

                    await ctx.reply(embed=embed, mention_author=False)
                    return

                async with self.utils.kamaitachi_client(ctx, target_id) as client:
                    resp = await client.get("https://kamai.tachi.ac/api/v1/users/me")
                    data = json_loads(resp.content)

                    if not data["success"]:
                        msg = f"Could not get user information from Kamaitachi: {data['success']}"
                        raise commands.CommandError(msg)

                    username = data["body"]["username"]

                    resp = await client.get(
                        f"https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single/pbs?search={urllib.parse.quote(song.title)}"
                    )
                    data = json_loads(resp.content)

                    if not data["success"]:
                        msg = f"Could not get scores from Kamaitachi: {data['description']}"
                        raise commands.CommandError(msg)

                    raw_records = convert_kt_pbs_to_records(data["body"])
                    records = [
                        pb for pb in raw_records if pb.extras[KEY_SONG_ID] == song.id
                    ]

                    if len(records) == 0:
                        msg = f"No records found for {username} on **{escape_markdown(song.title)}** on Kamaitachi."

                        if len(song.title) <= 5:
                            msg += " If you have a score on this song, it's probably because Tachi's PB search is buggy on short titles."

                        await ctx.reply(msg, mention_author=False)
                        return

                    network = " on Kamaitachi"
                    records = await self.utils.hydrate_records(records)
                    records.sort(key=lambda r: r.difficulty.value)
            else:
                async with self.utils.chuninet(ctx, target_id) as client:
                    userinfo = await client.authenticate()
                    username = userinfo.name
                    network = ""
                    records = await client.music_record(song.id)

                    if len(records) == 0:
                        await ctx.reply(
                            f"No records found for {userinfo.name}.",
                            mention_author=False,
                        )
                        return

                    records = await self.utils.hydrate_records(records)

            page = 0
            try:
                # intentionally passing an invalid color so it throws and keep the page at 0
                difficulty = Difficulty.from_embed_color(
                    embed.color.value if embed.color else 0  # type: ignore[attr-defined]
                )
                page = next(
                    (
                        i
                        for i, record in enumerate(records)
                        if record.difficulty == difficulty
                    ),
                    0,
                )
            except ValueError:
                pass

            view = EmbedPaginationView(ctx, [ScoreCardEmbed(r) for r in records])
            view.current_page = page

            if compare_message is not None:
                await view.start_from(
                    compare_message,
                    content=f"Top play for {username}{network}:",
                )
                return

            await view.start(content=f"Top play for {username}{network}:")
            return

    @commands.command("compare", aliases=["c"])
    @logged_prefix_command
    async def compare(self, ctx: Context, *, query: str = ""):
        """Compare your best score with another score.

        By default, it's the most recently posted score. You can reply to another
        user's score to compare with that instead. If there are multiple scores in
        said message, you will be prompted to select one.

        **Tip**: This command also works with some other bots (<@986651489529397279> and <@604641359416131585>
        to name a few). However, you will need to explicitly reply to those other bots' messages.
        If you don't reply, only recent scores *from this bot* will be checked.

        **Parameters**
        user: The user to compare with (defaults to you).
        `-k, --kamaitachi`: Get scores from Kamaitachi, if the target user has a linked account.
        """

        parser = DiscordArguments()
        parser.add_argument("-k", "--kamaitachi", action="store_true")

        try:
            args, rest = await parser.parse_known_intermixed_args(shlex_split(query))
        except ArgumentError as e:
            raise commands.BadArgument(str(e)) from e

        user = None

        if len(rest) > 0:
            for converter in [commands.MemberConverter, commands.UserConverter]:
                with contextlib.suppress(commands.BadArgument):
                    user = await converter().convert(ctx, rest[0])
                    break

        await self._compare_inner(ctx, user, kamaitachi=args.kamaitachi)

    @app_commands.command(
        name="compare", description="Compare your best score with another score."
    )
    @app_commands.describe(
        user="The user to compare with (defaults to you)",
        kamaitachi="Get scores from Kamaitachi, if the target user has a linked account",
    )
    @logged_app_command
    async def compare_slash(
        self,
        interaction: discord.Interaction,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        ctx = await Context.from_interaction(interaction)

        await self._compare_inner(ctx, user, kamaitachi=kamaitachi)

    async def song_title_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.autocompleters.song_title_autocomplete(interaction, current)

    async def _scores_inner(
        self,
        ctx: Context,
        query: str,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id

        kamaitachi = (
            await self.utils.choose_preferred_network(
                ctx, target_id, kamaitachi=kamaitachi
            )
            == "kamaitachi"
        )

        async with ctx.typing():
            guild_id = ctx.guild.id if ctx.guild else None
            result = await self.utils.find_songs(
                query, guild_id=guild_id, load_charts=True
            )

            if result.similarity < SIMILARITY_THRESHOLD:
                return await ctx.reply(
                    did_you_mean_text(result.songs[0], result.matched_alias),
                    mention_author=False,
                )

            # if we're fetching scores from Kamaitachi, we don't need to care about whether
            # the song is available in CHUNITHM International.
            #
            # However, we need to keep in mind that Kamaitachi does not support WORLD'S END.
            songs = [
                x
                for x in result.songs
                if (kamaitachi and x.genre != "WORLD'S END")
                or (not kamaitachi and x.available)
            ]

            if len(songs) > 1:
                options = []

                for i, x in enumerate(songs):
                    if x.genre == "WORLD'S END":
                        title = f"{x.title} [{x.charts[0].level}]"
                    else:
                        title = x.title

                    options.append((title, i))
                view = SelectToCompareView(
                    options=options,
                    placeholder="Select a song...",
                )
                select_message = await ctx.reply(
                    "Multiple songs were found. Select one:",
                    view=view,
                    mention_author=False,
                )

                await view.wait()

                if view.value is None:
                    with contextlib.suppress(discord.errors.NotFound):
                        await select_message.edit(
                            content="Timed out before selecting a song.",
                            view=None,
                            allowed_mentions=AllowedMentions.none(),
                        )
                    return None

                song = songs[int(view.value)]
            elif len(songs) > 0:
                song = songs[0]
                select_message = None
            else:
                msg = f"No songs currently available in CHUNITHM International matches the search criteria. Closest match was **{escape_markdown(result.songs[0].title)}**."
                raise commands.BadArgument(msg)

            if kamaitachi:
                async with self.utils.kamaitachi_client(ctx, target_id) as client:
                    resp = await client.get("https://kamai.tachi.ac/api/v1/users/me")
                    data = json_loads(resp.content)

                    if not data["success"]:
                        msg = f"Could not get user information from Kamaitachi: {data['success']}"
                        raise commands.CommandError(msg)

                    username = data["body"]["username"]

                    resp = await client.get(
                        f"https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single/pbs?search={urllib.parse.quote(song.title)}"
                    )
                    data = json_loads(resp.content)

                    if not data["success"]:
                        msg = f"Could not get scores from Kamaitachi: {data['description']}"
                        raise commands.CommandError(msg)

                    raw_records = convert_kt_pbs_to_records(data["body"])
                    records = [
                        pb for pb in raw_records if pb.extras[KEY_SONG_ID] == song.id
                    ]

                    if len(records) == 0:
                        msg = f"No records found for {username} on **{escape_markdown(song.title)}** on Kamaitachi."

                        if len(song.title) <= 5:
                            msg += " If you have a score on this song, it's probably because Tachi's PB search is buggy on short titles."

                        await ctx.reply(msg, mention_author=False)

                        return None

                    network = " on Kamaitachi"
                    records = await self.utils.hydrate_records(records)
                    records.sort(key=lambda r: r.difficulty.value)
            else:
                async with self.utils.chuninet(ctx, target_id) as client:
                    user_info = await client.authenticate()
                    username = user_info.name
                    network = ""
                    records = await client.music_record(song.id)

                    if len(records) == 0:
                        await ctx.reply(
                            f"No records found for {user_info.name} on **{escape_markdown(song.title)}**.",
                            mention_author=False,
                        )
                        return None

                    records = await self.utils.hydrate_records(records)

            view = EmbedPaginationView(ctx, [ScoreCardEmbed(r) for r in records])

            if select_message is not None:
                await view.start_from(
                    select_message,
                    content=f"Top play for {username}{network}:",
                )
            else:
                await view.start(
                    content=f"Top play for {username}{network}:",
                )

            return None

    @commands.command("scores", aliases=["score"])
    @logged_prefix_command
    async def scores(
        self,
        ctx: Context,
        *,
        query: str = "",
    ):
        """Get a player's scores for a specific song.

        **Parameters**:
        `user` (not required): The user to get scores for. Must go first if specified.
        `query` (required): The song to search for. You don't have to be exact; try things out!
        `-k, --kamaitachi`: Get scores from Kamaitachi, if the user has that linked.
        """

        parser = DiscordArguments()
        parser.add_argument("-k", "--kamaitachi", action="store_true")

        try:
            args, rest = await parser.parse_known_intermixed_args(shlex_split(query))
        except ArgumentError as e:
            raise commands.BadArgument(str(e)) from e

        user = None

        if len(rest) > 0:
            for converter in [commands.MemberConverter, commands.UserConverter]:
                with contextlib.suppress(commands.BadArgument):
                    user = await converter().convert(ctx, rest[0])
                    break

        if user is not None:
            if len(rest) < 2:
                msg = "You have not specified a song to search for."
                raise commands.BadArgument(msg)
            query = " ".join(rest[1:])
        else:
            query = " ".join(rest)

        query = await AliasNameConverter(lower=True).convert(ctx, query)

        await self._scores_inner(ctx, query, user, kamaitachi=args.kamaitachi)

    @app_commands.command(
        name="scores",
        description="Get personal bests for a specific song",
    )
    @app_commands.describe(
        query="The song to search for. You don't have to be exact; try things out!",
        user="The user to get scores for.",
        kamaitachi="Get scores from Kamaitachi, if the user has that linked.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.autocomplete(query=song_title_autocomplete)
    @logged_app_command
    async def scores_slash(
        self,
        interaction: discord.Interaction,
        query: app_commands.Transform[str, AliasNameTransformer(lower=True)],
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        ctx = await Context.from_interaction(interaction)

        await self._scores_inner(ctx, query, user, kamaitachi=kamaitachi)

    async def _best50_inner(
        self,
        ctx: Context,
        user: discord.User | discord.Member | None = None,
        *,
        image: bool | None = None,
        classic: bool = False,
        kamaitachi: bool = False,
        new_rating: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id

        async with ctx.typing():
            kamaitachi = (
                await self.utils.choose_preferred_network(
                    ctx, target_id, kamaitachi=kamaitachi
                )
                == "kamaitachi"
            )

            user_config = await self.utils.fetch_user_config(target_id)

            if kamaitachi:
                async with self.utils.kamaitachi_client(ctx, target_id) as client:
                    resp = await client.get("https://kamai.tachi.ac/api/v1/users/me")
                    data = json_loads(resp.content)
                    player_name = data["body"]["username"]
                    current_rating = None

                    if new_rating:
                        resp = await client.get(
                            "https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single/pbs/all"
                        )
                    else:
                        resp = await client.get(
                            "https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single/pbs/best?alg=rating"
                        )

                    data = json_loads(resp.content)

                if not data["success"]:
                    msg = f"Could not retrieve your best scores from Kamaitachi: {data['description']}"
                    raise commands.CommandError(msg)

                if new_rating:
                    raw_body = msgspec.convert(
                        data["body"], KTChunithmPersonalBestResponseBody
                    )
                    song_id_map = {s.id: s for s in raw_body.songs}
                    chart_id_map = {c.chart_id: c for c in raw_body.charts}

                    old_pbs = [
                        pb
                        for pb in raw_body.pbs
                        if song_id_map[pb.song_id].data.display_version
                        != CURRENT_CHUNITHM_VERSION_KT
                    ]
                    old_pbs.sort(
                        key=lambda pb: (
                            pb.calculated_data.rating,
                            pb.score_data.score,
                            chart_id_map[pb.chart_id].level_num,
                        ),
                        reverse=True,
                    )
                    records = [
                        convert_kt_to_record(
                            pb, song_id_map[pb.song_id], chart_id_map[pb.chart_id]
                        )
                        for pb in old_pbs[:30]
                    ]
                    records = await self.utils.hydrate_records(records)
                    record_slots = 30

                    new_pbs = [
                        pb
                        for pb in raw_body.pbs
                        if song_id_map[pb.song_id].data.display_version
                        == CURRENT_CHUNITHM_VERSION_KT
                    ]
                    new_pbs.sort(
                        key=lambda pb: (
                            pb.calculated_data.rating,
                            pb.score_data.score,
                            chart_id_map[pb.chart_id].level_num,
                        ),
                        reverse=True,
                    )
                    new_records = [
                        convert_kt_to_record(
                            pb, song_id_map[pb.song_id], chart_id_map[pb.chart_id]
                        )
                        for pb in new_pbs[:20]
                    ]
                    new_records = await self.utils.hydrate_records(new_records)
                    new_record_slots = 20

                    current_rating = float(
                        floor_to_ndp(
                            (
                                sum(
                                    (r.extras[KEY_PLAY_RATING] for r in records),
                                    Decimal(0),
                                )
                                + sum(
                                    (r.extras[KEY_PLAY_RATING] for r in new_records),
                                    Decimal(0),
                                )
                            )
                            / 50,
                            2,
                        )
                    )
                else:
                    pbs = convert_kt_pbs_to_records(data["body"])
                    pbs = await self.utils.hydrate_records(pbs)

                    records = pbs[:50]
                    record_slots = 50

                    new_records = None
                    new_record_slots = 0

                records = await self.utils.hydrate_records(records)
            else:
                async with self.utils.chuninet(ctx, target_id) as client:
                    player_data = await client.player_data()
                    player_name = player_data.name
                    current_rating = player_data.rating

                    records = await self.utils.hydrate_records(await client.best30())
                    record_slots = 30

                    new_records = await self.utils.hydrate_records(await client.new20())
                    new_record_slots = 20

            if classic:
                if new_records is not None:
                    view = B30N20View(ctx, records, new_records)
                else:
                    view = B30View(ctx, records, record_slots, show_reachable=False)

                await view.start()

                return

            b30_image = await asyncio.to_thread(
                render_b30,
                player_name,
                records=records,
                record_slots=record_slots,
                new_records=new_records,
                new_record_slots=new_record_slots,
                current_rating=current_rating,
                user_config=user_config,
            )
            generation_timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")

            if image:
                if ctx.interaction is None:
                    image_flag = "`-i` flag"
                    classic_flag = "`-c` flag"
                else:
                    image_flag = "`image: True` option"
                    classic_flag = "`classic: True` option"

                content = (
                    f"The {image_flag} is not needed anymore, because generating an image is now the default. "
                    "Using it will cause a hard error in a future update. "
                    f"If you wish to view your scores with Discord embeds, please use the {classic_flag}."
                )
            else:
                content = None

            await ctx.reply(
                content=content,
                file=discord.File(
                    b30_image, filename=f"chuni-penguin-b30-{generation_timestamp}.png"
                ),
                mention_author=False,
            )

    @commands.cooldown(15, 600, commands.BucketType.member)
    @commands.command("best50", aliases=["b30", "best30", "b50"])
    @logged_prefix_command
    async def best50(self, ctx: Context, *, query: str = ""):
        """View top 50 scores of you or another player.

        **Parameters**:
        `user`: The user to get scores for.
        `-c, --classic`: View your scores with Discord embeds instead of generating
        an image.
        `-k, --kamaitachi`: Get the best 50 scores from Kamaitachi, if the user
        has that linked.
        `-n, --new-rating`: For Kamaitachi, calculates best30 + new20 instead of best50.
        Does nothing for official network.
        """

        parser = DiscordArguments()
        parser.add_argument("-i", "--image", action="store_true")
        parser.add_argument("-c", "--classic", action="store_true")
        parser.add_argument("-k", "--kamaitachi", action="store_true")
        parser.add_argument("-n", "--new-rating", action="store_true")

        try:
            args, rest = await parser.parse_known_intermixed_args(shlex_split(query))
        except ArgumentError as e:
            raise commands.BadArgument(str(e)) from e

        user = None

        if len(rest) > 0:
            for converter in [commands.MemberConverter, commands.UserConverter]:
                with contextlib.suppress(commands.BadArgument):
                    user = await converter().convert(ctx, rest[0])
                    break

        await self._best50_inner(
            ctx,
            user,
            image=args.image,
            classic=args.classic,
            kamaitachi=args.kamaitachi,
            new_rating=args.new_rating,
        )

    @app_commands.command(name="best50", description="View top plays")
    @app_commands.checks.cooldown(15, 600, key=lambda i: i.user.id)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        user="The user to get best50 for",
        image="Render an image of your best 50 scores",
        classic="View your best 50 scores using Discord embeds instead of an image",
        kamaitachi="Get your best 50 from Kamaitachi if linked",
        new_rating="(Kamaitachi) Calculates best30+new20 instead of best50",
    )
    @app_commands.rename(new_rating="new-rating")
    @logged_app_command
    async def best50_slash(
        self,
        interaction: Interaction,
        user: discord.User | discord.Member | None = None,
        *,
        image: bool | None = None,
        classic: bool = False,
        kamaitachi: bool = False,
        new_rating: bool = False,
    ):
        ctx = await Context.from_interaction(interaction)

        await self._best50_inner(
            ctx,
            user,
            image=image,
            classic=classic,
            kamaitachi=kamaitachi,
            new_rating=new_rating,
        )

    @commands.command("recent10", aliases=["r10"], hidden=True)
    @logged_prefix_command
    async def recent10(self, ctx: Context):
        msg = (
            "This command has been disabled due to rating changes in CHUNITHM VERSE. "
            "It will be fully removed in a future update."
        )
        raise commands.CommandError(msg)

    @commands.command(
        "new20", aliases=["n10", "n15", "n20", "new10", "new15"], hidden=True
    )
    @logged_prefix_command
    async def new20(self, ctx: Context):
        msg = (
            "This command has been disabled because the new rating system is now official. "
            "It will be fully removed in a future update.\n\n"
            f"Please use the `{ctx.prefix}best50` command to see your new rating."
        )
        raise commands.CommandError(msg)

    @app_commands.command(name="top", description="View your best scores for a level.")
    @app_commands.describe(
        level="Level (from 1 to 15) to search for.",
        difficulty="Difficulty to search for.",
        genre="Genre to search for.",
        rank="Rank to search for.",
        sort="Sort records by a criteria (default rating).",
        kamaitachi="Get scores from Kamaitachi, if the target user has a linked account",
    )
    @app_commands.choices(
        level=[
            *[app_commands.Choice(name=str(i), value=str(i)) for i in range(1, 7)],
            *itertools.chain.from_iterable(
                [
                    (
                        app_commands.Choice(name=f"{i}", value=f"{i}"),
                        app_commands.Choice(name=f"{i}+", value=f"{i}+"),
                    )
                    for i in range(7, 16)
                ]
            ),
        ],
        difficulty=[
            app_commands.Choice(name=str(x), value=x.value)
            for x in Difficulty.__members__.values()
        ],  # type: ignore[reportGeneralTypeIssues]
        genre=[
            app_commands.Choice(name=str(x), value=x.value)
            for x in Genres.__members__.values()
        ],  # type: ignore[reportGeneralTypeIssues]
        rank=[
            app_commands.Choice(name=str(x), value=x.value)
            for x in Rank.__members__.values()
        ],  # type: ignore[reportGeneralTypeIssues]
    )
    @logged_app_command
    async def top_slash(
        self,
        interaction: "discord.Interaction[ChuniBot]",
        *,
        user: Optional[discord.User | discord.Member] = None,
        level: Optional[str] = None,
        difficulty: Optional[Difficulty] = None,
        genre: Optional[Genres] = None,
        rank: Optional[Rank] = None,
        sort: Literal["rating", "score", "overpower", "overpower %"] = "rating",
        kamaitachi: bool = False,
    ):
        ctx = await Context.from_interaction(interaction)
        target_user_id = interaction.user.id if user is None else user.id
        network = await self.utils.choose_preferred_network(
            ctx, target_user_id, kamaitachi=kamaitachi
        )

        if (
            level is None
            and difficulty is None
            and genre is None
            and rank is None
            and network == "chuninet"
        ):
            await self._best50_inner(ctx, user)
            return None

        await interaction.response.defer()

        if network == "chuninet" and (genre or rank) and not difficulty:
            return await interaction.followup.send(
                "Difficulty must be set if genre or rank is set."
            )

        if network == "chuninet":
            async with self.utils.chuninet(ctx, target_user_id) as client:
                records = await client.music_record_by_folder(
                    level=level, genre=genre, difficulty=difficulty, rank=rank
                )
                assert records is not None

                if len(records) == 0:
                    return await interaction.followup.send("No scores found.")

                records = await self.utils.hydrate_records(records)
        elif network == "kamaitachi":
            async with self.utils.kamaitachi_client(ctx, target_user_id) as client:
                resp = await client.get(
                    "https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single/pbs/all"
                )
                data = resp.json()
                records = convert_kt_pbs_to_records(data["body"])

                if level is not None:
                    records = [r for r in records if r.extras[KEY_LEVEL] == level]
                if difficulty is not None:
                    records = [r for r in records if r.difficulty == difficulty]
                if rank is not None:
                    records = [r for r in records if r.rank == rank]

                records = await self.utils.hydrate_records(records)

                if genre is not None:
                    records = [r for r in records if r.extras[KEY_SONG_GENRE] == genre]
        else:
            msg = "Invalid network. Expected chuninet or kamaitachi."
            raise ValueError(msg)

        if sort == "rating":
            records.sort(
                reverse=True,
                key=lambda x: (
                    x.extras.get(KEY_PLAY_RATING),
                    x.score,
                    x.extras.get(KEY_OVERPOWER_BASE),
                ),
            )
        elif sort == "score":
            records.sort(
                reverse=True,
                key=lambda x: (
                    x.score,
                    x.extras.get(KEY_PLAY_RATING),
                    x.extras.get(KEY_OVERPOWER_BASE),
                ),
            )
        elif sort == "overpower":
            records.sort(
                reverse=True,
                key=lambda x: (
                    x.extras.get(KEY_OVERPOWER_BASE),
                    x.extras.get(KEY_PLAY_RATING),
                    x.score,
                ),
            )
        elif sort == "overpower %":
            records.sort(
                reverse=True,
                key=lambda x: (
                    x.extras[KEY_OVERPOWER_BASE] / x.extras[KEY_OVERPOWER_MAX],
                    x.extras.get(KEY_OVERPOWER_BASE),
                    x.extras.get(KEY_PLAY_RATING),
                    x.score,
                ),
            )
        else:
            msg = f"Invalid sort type {sort}. Expected one of score, rating, overpower, overpower %."
            raise commands.BadArgument(msg)

        view = B30View(
            ctx, records, show_average=False, show_reachable=False, show_lamps=True
        )
        await view.start()
        return None

    @commands.command("top")
    @logged_prefix_command
    async def top(
        self,
        ctx: Context,
        *,
        query: str | None = None,
    ):
        """
        **View your best scores for a level.**

        **Parameters:**
        `user`: Discord username of the player. Yourself, if not provided.
        `level`: Level (from 1 to 15+) to search for.
        `-d`: Difficulty to search for. Must be one of `EASY`, `ADVANCED`, `EXPERT`, `MASTER`, `ULTIMA`, or `WE` if specified.
        `-g`: Genre to search for. Must be one of `POPS&ANIME`, `niconico`, `Touhou Project`, `ORIGINAL`, `VARIETY`, `Irodorimidori`, or `Gekimai`, if specified.
        `-r`: Rank to search for. Anywhere between "S" and "SSS+" (inclusive), if specified.
        `-s`: Choose a metric to sort scores by. Supported options are `score`, `rating`, `op`, `op_percent`.
        `-k`: Get scores from Kamaitachi, if the target user has a linked account.

        Genre and rank cannot be set at the same time. If genre or rank is set, difficulty must also be set.

        If multiple parameters are set, they will be applied in order of:
        - level
        - genre + difficulty
        - rank + difficulty
        - difficulty

        **Examples:**
        `c>top 14+`: View your best scores for level 14+
        `c>top -d mas`: View your best scores for MASTER difficulty
        `c>top -g original -d ultima`: View your best scores for ULTIMA difficulty in the ORIGINAL folder
        `c>top @player -r sss -d mas`: View @player's best scores for SSS rank on MASTER difficulty.
        """

        def sort_type(arg: str) -> str:
            if arg not in {
                "score",
                "rating",
                "op",
                "op_percent",
                "overpower",
                "overpower_percent",
            }:
                msg = "Invalid sort type. Expected one of score, rating, op, op_percent, overpower, overpower_percent."
                raise ValueError(msg)

            return arg

        if query is None:
            await self._best50_inner(ctx)
            return None

        parser = DiscordArguments()
        parser.add_argument("-d", "--difficulty", type=str, required=False)
        parser.add_argument("-s", "--sort", type=sort_type, required=False)
        parser.add_argument("-k", "--kamaitachi", action="store_true")

        group = parser.add_mutually_exclusive_group()
        group.add_argument("-g", "--genre", type=str, required=False)
        group.add_argument("-r", "--rank", type=str, required=False)

        try:
            args, rest = await parser.parse_known_intermixed_args(shlex_split(query))
        except ArgumentError as e:
            raise commands.BadArgument(str(e)) from e

        difficulty = (
            await DifficultyConverter().convert(ctx, args.difficulty)
            if args.difficulty
            else None
        )
        genre = await GenreConverter().convert(ctx, args.genre) if args.genre else None
        rank = await RankConverter().convert(ctx, args.rank) if args.rank else None

        if (args.genre or args.rank) and not difficulty:
            msg = "Must specify a difficulty when searching by genre or rank."
            raise commands.BadArgument(msg)

        user = None
        str_level = None

        if len(rest) > 0:
            for converter in [commands.MemberConverter, commands.UserConverter]:
                with contextlib.suppress(commands.BadArgument):
                    user = await converter().convert(ctx, rest[0])
                    rest = rest[1:]
                    break

        str_level = rest[0] if len(rest) > 0 else None
        target_user_id = ctx.author.id if user is None else user.id
        network = await self.utils.choose_preferred_network(
            ctx, target_user_id, kamaitachi=args.kamaitachi
        )

        if (
            user is not None
            and str_level is None
            and difficulty is None
            and genre is None
            and rank is None
            and network == "chuninet"
        ):
            await self._best50_inner(ctx, user)
            return None

        level = None
        internal_level: float | None = None

        if str_level:
            # Three accepted use cases, "14", "14+" and "14.9"
            msg = "Invalid level."

            if "." in str_level and str_level.replace(".", "", 1).isdigit():
                internal_level = float(str_level)
                level = str(int(internal_level))

                if internal_level * 10 % 10 >= 5:
                    level += "+"
            elif str_level[-1] == "+" and str_level[:-1].isdigit():
                if int(str_level[:-1]) not in range(7, 16):
                    raise commands.BadArgument(msg)

                level = str_level
            elif str_level.isdigit():
                if int(str_level) not in range(1, 16):
                    raise commands.BadArgument(msg)

                level = str_level
            else:
                raise commands.BadArgument(msg)

        async with ctx.typing():
            if network == "chuninet":
                async with self.utils.chuninet(ctx, target_user_id) as client:
                    records = await client.music_record_by_folder(
                        level=level,
                        genre=genre,
                        difficulty=difficulty,
                        rank=rank,
                    )
                    assert records is not None

                    if len(records) == 0:
                        return await ctx.reply("No scores found.", mention_author=False)

                    records = await self.utils.hydrate_records(records)
            elif network == "kamaitachi":
                async with self.utils.kamaitachi_client(ctx, target_user_id) as client:
                    resp = await client.get(
                        "https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single/pbs/all"
                    )
                    data = resp.json()
                    records = convert_kt_pbs_to_records(data["body"])

                    if level is not None:
                        records = [r for r in records if r.extras[KEY_LEVEL] == level]
                    if difficulty is not None:
                        records = [r for r in records if r.difficulty == difficulty]
                    if rank is not None:
                        records = [r for r in records if r.rank == rank]

                    records = await self.utils.hydrate_records(records)

                    if genre is not None:
                        records = [
                            r for r in records if r.extras[KEY_SONG_GENRE] == genre
                        ]

                    if len(records) == 0:
                        return await ctx.reply("No scores found.", mention_author=False)
            else:
                msg = "Invalid network. Expected chuninet or kamaitachi."
                raise ValueError(msg)

            if args.sort is None or args.sort == "rating":
                records.sort(
                    reverse=True,
                    key=lambda x: (
                        x.extras.get(KEY_PLAY_RATING, Decimal(0)),
                        x.score,
                        x.extras.get(KEY_OVERPOWER_BASE, Decimal(0)),
                    ),
                )
            elif args.sort == "score":
                records.sort(
                    reverse=True,
                    key=lambda x: (
                        x.score,
                        x.extras.get(KEY_PLAY_RATING, Decimal(0)),
                        x.extras.get(KEY_OVERPOWER_BASE, Decimal(0)),
                    ),
                )
            elif args.sort in {"overpower", "op"}:
                records.sort(
                    reverse=True,
                    key=lambda x: (
                        x.extras.get(KEY_OVERPOWER_BASE, Decimal(0)),
                        x.extras.get(KEY_PLAY_RATING, Decimal(0)),
                        x.score,
                    ),
                )
            elif args.sort in {"overpower_percent", "op_percent"}:
                records.sort(
                    reverse=True,
                    key=lambda x: (
                        x.extras.get(KEY_OVERPOWER_BASE, Decimal(0))
                        / x.extras.get(KEY_OVERPOWER_MAX, Decimal(1)),
                        x.extras.get(KEY_OVERPOWER_BASE, Decimal(0)),
                        x.extras.get(KEY_PLAY_RATING, Decimal(0)),
                        x.score,
                    ),
                )
            else:
                msg = f"Invalid sort type {args.sort}. Expected one of score, rating, op, op_percent, overpower, overpower_percent."
                raise commands.BadArgument(msg)

            if internal_level is not None:
                records = [
                    r
                    for r in records
                    if r.extras.get(KEY_INTERNAL_LEVEL) == internal_level
                ]

                if len(records) == 0:
                    return await ctx.reply("No scores found.", mention_author=False)

            view = B30View(
                ctx, records, show_average=False, show_reachable=False, show_lamps=True
            )
            await view.start()
            return None

    @commands.hybrid_command("leaderboard", aliases=["lb"])
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name="BASIC", value="BASIC"),
            app_commands.Choice(name="ADVANCED", value="ADVANCED"),
            app_commands.Choice(name="EXPERT", value="EXPERT"),
            app_commands.Choice(name="MASTER", value="MASTER"),
            app_commands.Choice(name="ULTIMA", value="ULTIMA"),
        ]
    )
    @app_commands.autocomplete(query=song_title_autocomplete)
    @logged_prefix_command
    async def leaderboard(
        self,
        ctx: Context,
        difficulty: Annotated[Difficulty, DifficultyConverter],
        *,
        query: Annotated[str, AliasNameConverter(lower=True)],
    ):
        """View the international leaderboard for a specific song and difficulty.

        Currently requires logging in to CHUNITHM-NET, though this might be changed.

        Parameters
        ----------
        difficulty: str
            Chart difficulty to search for (BAS/ADV/EXP/MAS/ULT).
        query: str
            Song title to search for. You don't have to be exact; try things out!
        """
        async with ctx.typing(), self.utils.chuninet(ctx) as client:
            guild_id = ctx.guild.id if ctx.guild else None
            song, alias, similarity = await self.utils.find_song(
                query, guild_id=guild_id, worlds_end=False
            )

            if song is None or similarity < SIMILARITY_THRESHOLD:
                await ctx.reply(did_you_mean_text(song, alias), mention_author=False)
                return

            song.raise_if_not_available()

            async with self.bot.begin_db_session() as session:
                stmt = (
                    select(Chart)
                    .where(
                        (Chart.song_id == song.id)
                        & (Chart.difficulty == difficulty.short_form())
                    )
                    .options(
                        joinedload(Chart.song), joinedload(Chart.sdvxin_chart_view)
                    )
                )
                chart = (await session.execute(stmt)).scalar_one_or_none()

            leaderboard = await client.music_leaderboard(song.id, difficulty)
            view = LeaderboardView(ctx, leaderboard, song, difficulty, chart)
            await view.start()


async def setup(bot: "ChuniBot"):
    await bot.add_cog(RecordsCog(bot))
