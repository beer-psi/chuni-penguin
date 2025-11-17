from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from chuni_penguin.constants import ASSETS_DIR, CACHE_DIR
from chuni_penguin.networks.consts import (
    KEY_INTERNAL_LEVEL,
    KEY_PLAY_RATING,
    KEY_SONG_ID,
)
from chuni_penguin.networks.types import ComboLamp, Score
from chuni_penguin.utils import floor_to_ndp

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chuni_penguin.database import UserConfig

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

B30_IMAGE_WIDTH = 1872
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


# Used to cache crops of the best50 background and overlay because apparently
# resizing images is very expensive
def _make_background_image(file: Path, width: int, height: int):
    cached_file = (
        CACHE_DIR
        / "b50"
        / f"{file.stem}_{file.stat().st_mtime}_preprocessed_{width}x{height}.webp"
    )

    if cached_file.exists():
        im = Image.open(cached_file)

        if im.mode != "RGBA":
            im = im.convert("RGBA")

        return im

    with Image.open(file) as im:
        im = im.resize((im.width * height // im.height, height))
        im = im.crop(
            (
                (im.width - width) / 2,
                (im.height - height) / 2,
                (im.width + width) / 2,
                (im.height + height) / 2,
            )
        )
        im = im.filter(ImageFilter.GaussianBlur(5))
        im.save(cached_file, lossless=True)

    return im


def _render_b30_entry(
    b30_image: Image.Image,
    record: Score,
    i: int,
    x: int,
    y: int,
    user_config: "UserConfig | None" = None,
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
        elif user_config.synthesis_alt_jacket == "musicdiver":
            jacket_basename = "2698_musicdiver"
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
                jacket = jacket.resize(
                    (B30_JACKET_WIDTH, B30_JACKET_HEIGHT), Image.Resampling.LANCZOS
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

    if record.combo_lamp != ComboLamp.none:
        rank_lamp_width = b30_draw.textlength(rank_lamp + " ", NOTO_SANS_JP_24)

        if record.combo_lamp == ComboLamp.all_justice_critical:
            combo_lamp = "[AJC]"
            combo_lamp_color = "#FFDF75"
        elif record.combo_lamp == ComboLamp.all_justice:
            combo_lamp = "[AJ]"
            combo_lamp_color = "#FFDF75"
        elif record.combo_lamp == ComboLamp.full_combo:
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

    if record.achieved_at is not None:
        difference = datetime.now(UTC) - record.achieved_at

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

    if (judgements := record.judgements) is not None:
        if extra_info:
            extra_info += f" | {judgements.justice_critical} – {judgements.justice} – {judgements.attack} – {judgements.miss}"  # noqa: RUF001
        else:
            extra_info += f"{judgements.justice_critical} – {judgements.justice} – {judgements.attack} – {judgements.miss}"  # noqa: RUF001

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
    records: "Sequence[Score]",
    record_slots: int = 30,
    new_records: "Sequence[Score] | None" = None,
    new_record_slots: int = 20,
    current_rating: float | None = None,
    user_config: "UserConfig | None" = None,
):
    if len(records) > record_slots:
        msg = "More records provided than number of record slots"
        raise ValueError(msg)

    if new_records is not None and len(new_records) > new_record_slots:
        msg = "More new records provided than number of new record slots"
        raise ValueError(msg)

    row_num = ceil(record_slots / 5)

    # calculate image height
    b30_image_height = (
        B30_HEADER_HEIGHT
        + B30_HEADER_SPACING
        + (B30_ENTRY_HEIGHT + B30_ENTRY_HEIGHT_SPACING) * row_num
        + B30_FOOTER_SPACING
        + B30_FOOTER_HEIGHT
    )

    # Add a gap between old rating and new rating, if it is provided
    if new_records is not None:
        new_row_num = ceil(new_record_slots / 5)
        b30_image_height += B30_OLD_NEW_SPACING + (B30_ENTRY_HEIGHT + 15) * new_row_num

    # draw background, copy so we can paste things on top of it
    b30_image = _make_background_image(
        ASSETS_DIR / "b50" / "b50_bg.png", B30_IMAGE_WIDTH, b30_image_height
    ).copy()

    # draw background overlay
    b30_overlay = _make_background_image(
        ASSETS_DIR / "b50" / "b50_overlay.png", b30_image.width, b30_image.height
    )

    b30_image = Image.alpha_composite(b30_image, b30_overlay)

    # draw header overlay
    with Image.open(ASSETS_DIR / "b50" / "b50_part_header.png") as im:
        header_padded = Image.new("RGBA", b30_image.size)
        header_padded.paste(im, (0, 0))
        b30_image = Image.alpha_composite(b30_image, header_padded)

    # draw logo
    with Image.open(ASSETS_DIR / "b50" / "b50_logo.png") as im:
        logo_padded = Image.new("RGBA", b30_image.size)
        # the original verse icon was 400x289. for best results other logos should
        # also be scaled to x289.
        logo_padded.paste(
            im, (1442 + (400 - im.width) // 2, 10 + (289 - im.height) // 2)
        )
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

        with Image.open(digit_path) as digit_im:
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
        "Design by Tukkun | Generated by chuni penguin#3127",
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

    buffer = BytesIO()

    b30_image.save(buffer, "PNG", compress_level=3)
    buffer.seek(0)

    return buffer
