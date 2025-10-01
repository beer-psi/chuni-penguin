# Utilities for basic operations on OggOpus files
# - Determining the length of the file
# - Clipping a segment of the audio file
#
# This makes a lot of assumptions about its inputs, namely that
# - The ogg provided only has a single track
# - The audio encoding is opus
# which is what you *should* have if you used the asset tools in this repository.
#
# If you use different audio files and formats, feel free to just use ffmpeg, but
# I don't want to carry around ~150MB just to deal with some oggs.
import base64
import audioop
import io
import itertools
import os
import struct
from collections import deque
from enum import IntFlag, auto
from pathlib import Path
from typing import IO, Final, TypeVar

import discord
from discord.oggparse import OggError

try:
    from penguin_native import crc32_ogg  # pyright: ignore[reportMissingImports]
except ImportError:
    from functools import lru_cache

    @lru_cache(maxsize=None)
    def create_crc32_table(poly: int):
        table: list[int] = []

        for i in range(256):
            k = i << 24

            for _ in range(8):
                k = (k << 1) ^ poly if k & 0x80000000 else k << 1

            table.append(k & 0xFFFFFFFF)

        return table

    def crc32_ogg(data: bytes | bytearray, init: int = 0):
        table = create_crc32_table(0x04C11DB7)

        for byte in memoryview(data):
            lookup_index = ((init >> 24) ^ byte) & 0xFF
            init = ((init & 0xFFFFFF) << 8) ^ table[lookup_index]

        return init


# up to the number of segments
OGG_HEADER_FORMAT: Final = struct.Struct("<BBQIIIB")
OGG_HEADER_BEFORE_CHECKSUM_FORMAT: Final = struct.Struct("<BBQII")

# 27 bytes from the capture pattern b"OggS" to the number of segments.
# There can be 255 segments maximum, meaning that
# - 255 bytes to encode each segment's length
# - 255 bytes for each segment itself
OGG_PAGE_MAX_SIZE: Final = 4 + OGG_HEADER_FORMAT.size + 255 + 255 * 255

OPUS_HEAD_FORMAT: Final = struct.Struct("<BBHIhB")
OPUS_MAPPING_TABLE_FORMAT: Final = struct.Struct("<BB")

# https://datatracker.ietf.org/doc/html/rfc6716#section-3.1
# fmt: off
CONFIGURATION_NUMBER_TO_FRAME_DURATION: Final = [
    10, 20, 40, 60,
    10, 20, 40, 60,
    10, 20, 40, 60,
    10, 20,
    10, 20,
    2.5, 5, 10, 20,
    2.5, 5, 10, 20,
    2.5, 5, 10, 20,
    2.5, 5, 10, 20,
]
# fmt: on


class OggHeaderType(IntFlag):
    NONE = 0
    CONTINUATION = auto()
    BEGIN_OF_STREAM = auto()
    END_OF_STREAM = auto()


class OggPage:
    def __init__(
        self,
        *,
        version: int,
        header_type: OggHeaderType,
        granule_position: int,
        bitstream_serial_number: int,
        page_sequence_number: int,
    ):
        self.version: int = version
        self.header_type: OggHeaderType = header_type
        self.granule_position: int = granule_position
        self.bitstream_serial_number: int = bitstream_serial_number
        self.page_sequence_number: int = page_sequence_number

        self._segment_table: list[int] = []
        self._data: bytes = b""

    @classmethod
    def load(cls, f: IO[bytes]):
        # The 4 is for the OggS capturing pattern
        header_bytes = f.read(4 + OGG_HEADER_FORMAT.size)

        if header_bytes[:4] != b"OggS":
            msg = "Invalid Ogg page; must start with capturing pattern OggS"
            raise ValueError(msg)

        (
            version,
            header_type,
            granule_position,
            bitstream_serial_number,
            page_sequence_number,
            expected_checksum,
            page_segments,
        ) = OGG_HEADER_FORMAT.unpack_from(header_bytes, 4)

        if (version & 0xF0) != 0:
            msg = f"Unsupported Ogg version {version}"
            raise ValueError(msg)

        segment_table_bytes = f.read(page_segments)
        segment_table = list(segment_table_bytes)

        data = f.read(sum(segment_table))
        checksum = crc32_ogg(
            b"".join(
                [
                    header_bytes[: OGG_HEADER_BEFORE_CHECKSUM_FORMAT.size + 4],
                    b"\x00\x00\x00\x00",
                    header_bytes[OGG_HEADER_BEFORE_CHECKSUM_FORMAT.size + 8 :],
                    segment_table_bytes,
                    data,
                ]
            )
        )

        if checksum != expected_checksum:
            msg = f"Corrupt Ogg page: {checksum=} != {expected_checksum=}"
            raise ValueError(msg)

        page = cls(
            version=version,
            header_type=OggHeaderType(header_type),
            granule_position=granule_position,
            bitstream_serial_number=bitstream_serial_number,
            page_sequence_number=page_sequence_number,
        )
        page._segment_table = segment_table
        page._data = data

        return page

    def dump(self, f: IO[bytes]):
        packet_start = f.tell()

        f.write(b"OggS")

        header_bytes = OGG_HEADER_FORMAT.pack(
            self.version,
            self.header_type.value,
            self.granule_position,
            self.bitstream_serial_number,
            self.page_sequence_number,
            0,
            len(self._segment_table),
        )
        f.write(header_bytes)

        segment_table_bytes = bytes(self._segment_table)
        f.write(segment_table_bytes)

        f.write(self._data)

        packet_end = f.tell()
        checksum = crc32_ogg(
            b"".join([b"OggS", header_bytes, segment_table_bytes, self._data])
        )

        f.seek(packet_start + 4 + OGG_HEADER_BEFORE_CHECKSUM_FORMAT.size)
        f.write(checksum.to_bytes(4, "little"))
        f.seek(packet_end)

    def dumps(self):
        bio = io.BytesIO()

        self.dump(bio)
        return bio.getvalue()

    def add_packet(self, data: bytes | bytearray):
        # for packets longer than 255 bytes, you need to split into multiple
        # segments of 255, terminating in a <255 length segment.
        # even for packets that are exactly 255 bytes, you need to encode them as
        # (255, 0)

        segment_table: list[int] = []

        if len(data) >= 255:
            segment_table += [255 for _ in range(len(data) // 255)]
            segment_table.append(len(data) % 255)
        else:
            segment_table.append(len(data))

        if len(segment_table) + len(self._segment_table) > 255:
            msg = "Maximum number of segments exceeded"
            raise OggError(msg)

        self._segment_table += segment_table
        self._data += data

    def iter_packets(self):
        packet_length = offset = 0

        for segment_length in self._segment_table:
            if segment_length == 255:
                packet_length += 255
                continue

            packet_length += segment_length
            yield self._data[offset : offset + packet_length]
            offset += packet_length
            packet_length = 0


class OggStream:
    def __init__(self, f: IO[bytes]):
        self._f: IO[bytes] = f

    def iter_pages(self):
        while True:
            try:
                _step_to_next_page(self._f)
            except OggError:
                return None

            yield OggPage.load(self._f)


def _step_to_next_page(f: IO[bytes]):
    """
    Given a seekable file-like object, step through the file until the stream's
    position is at the start of an Ogg page.
    """

    capture_pattern = deque(maxlen=4)
    found = False

    while data := f.read(1):
        capture_pattern.append(data[0])

        if len(capture_pattern) < 4:
            continue

        if (
            capture_pattern[0] == 79
            and capture_pattern[1] == 103
            and capture_pattern[2] == 103
            and capture_pattern[3] == 83
        ):
            found = True

            f.seek(-4, os.SEEK_CUR)
            break

    if not found:
        msg = "Could not locate next Ogg page"
        raise OggError(msg)


def _opus_packet_duration(packet: bytes) -> float:
    if not packet:
        msg = "invalid opus packet: missing TOC byte"
        raise OggError(msg)

    toc_byte = packet[0]
    configuration_number = toc_byte >> 3
    frame_duration = CONFIGURATION_NUMBER_TO_FRAME_DURATION[configuration_number]

    # https://datatracker.ietf.org/doc/html/rfc6716#section-3.1
    c = toc_byte & 0b11

    if c == 0:
        num_frames = 1
    elif c in (1, 2):
        num_frames = 2
    else:
        # https://datatracker.ietf.org/doc/html/rfc6716#section-3.2.5
        if len(packet) < 2:
            msg = (
                "opus code 3 packet with no following byte containing number of frames"
            )
            raise OggError(msg)

        num_frames = packet[1] & 0b111111

    return frame_duration * num_frames


def get_audio_duration(file: str | Path) -> float:
    """
    Get the audio duration, in seconds, of the provided OggOpus file.
    """

    if isinstance(file, str):
        file = Path(file)

    with file.open("rb") as f:
        stream = OggStream(f)
        iter_pages = stream.iter_pages()
        page = next(iter_pages)

        iter_packets = page.iter_packets()
        header_packet = next(iter_packets)

        if header_packet[:8] != b"OpusHead":
            msg = f"Input is not an OggOpus file. Expected first packet to start with OpusHead, got {header_packet[:8]}."
            raise OggError(msg)

        (
            version,
            _channel_count,
            _pre_skip,
            _input_sample_rate,
            _output_gain,
            _mapping_family,
        ) = OPUS_HEAD_FORMAT.unpack_from(header_packet, 8)

        # Implementations SHOULD treat streams where the upper four bits of the version
        # number match that of a recognized specification as backwards compatible with
        # that specification.
        #
        # Section 5.1.2, RFC 7845
        if (version & 0xF0) != 0:
            msg = f"Unsupported Opus version {version}"
            raise OggError(msg)

        # Go to the end of the ogg to find the last ogg page
        _ = f.seek(-OGG_PAGE_MAX_SIZE, os.SEEK_END)

        # Scan through until we find our familiar sequence OggS
        _step_to_next_page(f)

        last_page: OggPage | None = None

        # private usage or something, though I doubt there needs to be an update
        # to an ogg parser
        for page in stream.iter_pages():
            last_page = page

    # Debug assert: since we seeked back for the maximum length of an ogg page,
    # there must be at least one page. If there isn't, the ogg is either corrupt
    # (which OggStream should have flagged), or some other thing out of our control
    # happened.
    assert last_page is not None

    if (
        last_page.granule_position == -1
        or OggHeaderType.END_OF_STREAM not in last_page.header_type
    ):
        msg = "Truncated Ogg file."
        raise OggError(msg)

    # The granule position of an audio data page is in units of PCM audio
    # samples at a fixed rate of 48 kHz
    #
    # Section 4, RFC 7845
    return last_page.granule_position / 48000


T = TypeVar("T", bound=IO[bytes])


def crop_audio(file: str | Path, start: float, duration: float, output: T) -> T:
    """
    Equivalent to `ffmpeg -ss $start -i $file -t $duration`, but for Ogg Opus
    files only.

    Returns a byte string containing an OggOpus starting at the specified `start`,
    with a duration of at most `duration` seconds.
    """

    if isinstance(file, str):
        file = Path(file)

    start_ms = start * 1000
    target_duration_ms = duration * 1000

    with file.open("rb") as f:
        stream = OggStream(f)
        header_page = next(stream.iter_pages())
        header_packet = next(header_page.iter_packets())

        if header_packet[:8] != b"OpusHead":
            msg = f"Input is not an OggOpus file. Expected first packet to start with OpusHead, got {header_packet[:8]}."
            raise OggError(msg)

        metadata_page = next(stream.iter_pages())
        metadata_packet = next(metadata_page.iter_packets())

        if metadata_packet[:8] != b"OpusTags":
            msg = f"Input is not an OggOpus file. Expected second packet to start with OpusTags, got {metadata_packet[:8]}."
            raise OggError(msg)

        (
            version,
            _channel_count,
            _pre_skip,
            _input_sample_rate,
            _output_gain,
            _mapping_family,
        ) = OPUS_HEAD_FORMAT.unpack_from(header_packet, 8)

        # Implementations SHOULD treat streams where the upper four bits of the version
        # number match that of a recognized specification as backwards compatible with
        # that specification.
        #
        # Section 5.1.2, RFC 7845
        if (version & 0xF0) != 0:
            msg = f"Unsupported Opus version {version}"
            raise OggError(msg)

        start_granule_pos = int(start * 48000)

        # Seek to the Ogg page containing the given start time using bisection.
        start_byte_pos = 0
        end_byte_pos = f.seek(0, os.SEEK_END)

        # Bisect the stream only when the byte range is large. For smaller ranges,
        # a linear scan is faster than having the bisection converge.
        while end_byte_pos - start_byte_pos > 2 * OGG_PAGE_MAX_SIZE:
            mid_byte_pos = (start_byte_pos + end_byte_pos) // 2

            # Seek to the middle of the byte range.
            _ = f.seek(mid_byte_pos)

            # Get the next page starting from the midpoint.
            try:
                _step_to_next_page(f)
            except OggError:  # oops, there's nothing left to the right
                end_byte_pos = mid_byte_pos
                continue

            page = OggPage.load(f)

            if start_granule_pos < page.granule_position:
                # Our target is to the left of the current page.
                end_byte_pos = mid_byte_pos
            elif start_granule_pos > page.granule_position:
                # Our target is to the right of the current page.
                start_byte_pos = mid_byte_pos
            else:
                start_byte_pos = end_byte_pos = mid_byte_pos
                break

        if start_byte_pos != end_byte_pos:
            # The bisection didn't converge.
            _ = f.seek(start_byte_pos)

            # If there isn't another page after start_byte_pos, bail
            try:
                _step_to_next_page(f)
            except OggError:
                msg = "start position is out of range"
                raise OggError(msg) from None

        # iterate through each packet to find our target timestamp
        bitstream_serial_number = header_page.bitstream_serial_number

        header_page.dump(output)
        metadata_page.dump(output)

        found_packet = False
        page_sequence_number = metadata_page.page_sequence_number + 1
        output_page = OggPage(
            version=0,
            header_type=OggHeaderType(0),
            granule_position=0,
            bitstream_serial_number=bitstream_serial_number,
            page_sequence_number=page_sequence_number,
        )
        page_duration_ms = 0
        total_duration_ms = 0

        def write_opus_packet(packet: bytes, packet_duration: float | None = None):
            nonlocal output_page
            nonlocal page_duration_ms
            nonlocal total_duration_ms
            nonlocal page_sequence_number

            if packet_duration is None:
                packet_duration = _opus_packet_duration(packet)

            output_page.add_packet(packet)

            page_duration_ms += packet_duration
            total_duration_ms += packet_duration

            if total_duration_ms >= target_duration_ms:  # we're done
                output_page.header_type = OggHeaderType.END_OF_STREAM
                output_page.granule_position = int(total_duration_ms * 48)
                output_page.dump(output)
                return output

            # we can be smarter about how to segment packets, but I think
            # ~1 second per page is a reasonable way to segment it
            if page_duration_ms >= 1000:
                # the granule position is always according to a 48000hz sample rate
                output_page.granule_position = int(total_duration_ms * 48)
                output_page.dump(output)

                page_sequence_number += 1
                page_duration_ms = 0
                output_page = OggPage(
                    version=0,
                    header_type=OggHeaderType(0),
                    granule_position=0,
                    bitstream_serial_number=bitstream_serial_number,
                    page_sequence_number=page_sequence_number,
                )

            return None

        for page in stream.iter_pages():
            if start_granule_pos > page.granule_position:
                continue

            packet_durations_ms: list[float] = []

            if found_packet:
                for packet in page.iter_packets():
                    if (result := write_opus_packet(packet)) is not None:
                        return result

                # continue copying packets, don't do any of the seekings
                continue

            # logic for seeking to the target packet
            packet_durations_ms = [
                _opus_packet_duration(packet) for packet in page.iter_packets()
            ]
            page_end_time_ms = page.granule_position / 48
            packet_times_ms: list[float] = [
                page_end_time_ms - duration_ms
                for duration_ms in itertools.accumulate(reversed(packet_durations_ms))
            ]
            start_packet_idx = -1

            # since we were calculating the packet times from backwards to forwards,
            # reverse the list so that we're in the right spot
            packet_times_ms.reverse()

            for i, time_ms in enumerate(packet_times_ms):
                if time_ms >= start_ms:
                    start_packet_idx = i
                    break

            if start_packet_idx == -1:
                continue

            found_packet = True

            for i, (packet, dur_ms) in enumerate(
                zip(page.iter_packets(), packet_durations_ms, strict=True)
            ):
                if i < start_packet_idx:
                    continue

                if (result := write_opus_packet(packet, dur_ms)) is not None:
                    return result

    if not found_packet:
        msg = "could not reach seek target after exhausting original ogg file"
        raise OggError(msg)

    # might have exhausted the stream without meeting the duration, in which case
    # just return what we have
    return output


def generate_waveform(fp: IO[bytes], duration: float):
    """
    Generate a Discord voice message waveform given the audio and duration in seconds.
    """

    pos = fp.tell()

    stream = OggStream(fp)
    header_page = next(stream.iter_pages())
    header_packet = next(header_page.iter_packets())

    if header_packet[:8] != b"OpusHead":
        msg = f"Input is not an OggOpus file. Expected first packet to start with OpusHead, got {header_packet[:8]}."
        raise OggError(msg)

    metadata_page = next(stream.iter_pages())
    metadata_packet = next(metadata_page.iter_packets())

    if metadata_packet[:8] != b"OpusTags":
        msg = f"Input is not an OggOpus file. Expected second packet to start with OpusTags, got {metadata_packet[:8]}."
        raise OggError(msg)

    (
        version,
        _channel_count,
        _pre_skip,
        input_sample_rate,
        _output_gain,
        _mapping_family,
    ) = OPUS_HEAD_FORMAT.unpack_from(header_packet, 8)

    # Implementations SHOULD treat streams where the upper four bits of the version
    # number match that of a recognized specification as backwards compatible with
    # that specification.
    #
    # Section 5.1.2, RFC 7845
    if (version & 0xF0) != 0:
        msg = f"Unsupported Opus version {version}"
        raise OggError(msg)

    # The waveform is intended to be a preview of the entire voice message,
    # with 1 byte per datapoint encoded in base64. Clients sample the recording at most
    # once per 100 milliseconds, but will downsample so that no more than
    # 256 datapoints are in the waveform.
    #
    # ... that is what Discord docs say, but I've found that for shorter durations
    # it's usually 150-200ms per sample. Let's go with 150ms.
    ms_per_sample = duration * 100 // 256 if duration >= 256 else 150
    decoder = discord.opus.Decoder()
    waveform = bytearray()
    samples = bytearray()
    current_time_ms: float = 0

    for page in stream.iter_pages():
        for packet in page.iter_packets():
            # pcm s16le
            pcm = decoder.decode(packet, fec=False)
            num_samples = len(pcm) // 2
            current_time_ms += num_samples * 1000 / input_sample_rate

            samples.extend(pcm)

            if current_time_ms >= ms_per_sample:
                avg = audioop.max(samples, 2)

                waveform.append(abs(avg) * 254 // 32767 + 1)
                samples.clear()
                current_time_ms = 0

    # double the waveform if the audio is quiet
    if not any(wave >= 128 for wave in waveform):
        waveform = bytearray([wave * 2 for wave in waveform])

    if fp.seekable:
        fp.seek(pos)

    return base64.b64encode(waveform).decode("ascii")
