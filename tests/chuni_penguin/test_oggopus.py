import hashlib
import io
import random
import shutil
import subprocess
from pathlib import Path

import msgspec
import pytest

from chuni_penguin.oggopus import OggStream, crop_audio, get_audio_duration

audio_files = list(Path("assets/audio").glob("*.ogg"))

if len(audio_files) == 0:
    pytest.skip(reason="No test files", allow_module_level=True)  # pragma: no cover


@pytest.mark.parametrize("input", random.choices(audio_files, k=20))
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_get_audio_duration(input: Path):
    duration = get_audio_duration(input)
    duration_ffmpeg = float(
        msgspec.json.decode(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-i",
                    str(input),
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_error",
                    "-loglevel",
                    "fatal",
                ]
            )
        )["format"]["duration"]
    )

    assert pytest.approx(duration) == duration_ffmpeg


@pytest.mark.parametrize("input", random.choices(audio_files, k=20))
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_crop_audio(input: Path):
    duration = get_audio_duration(input)
    crop_duration = random.randrange(1, 15)
    crop_start = random.randrange(0, int(duration - crop_duration))

    crop = io.BytesIO()
    crop_audio(input, crop_start, crop_duration, crop)
    crop.seek(0)

    ffmpeg_crop = io.BytesIO(
        subprocess.check_output(
            [
                "ffmpeg",
                "-ss",
                str(crop_start),
                "-i",
                str(input),
                "-t",
                str(crop_duration),
                "-f",
                "ogg",
                "-c",
                "copy",
                "pipe:1",
            ]
        )
    )

    hash = hashlib.sha256()
    ffmpeg_hash = hashlib.sha256()

    for page, ffmpeg_page in zip(
        OggStream(crop).iter_pages(), OggStream(ffmpeg_crop).iter_pages(), strict=False
    ):
        for packet, ffmpeg_packet in zip(
            page.iter_packets(), ffmpeg_page.iter_packets(), strict=True
        ):
            hash.update(packet)
            ffmpeg_hash.update(ffmpeg_packet)

    assert hash.digest() == ffmpeg_hash.digest()
