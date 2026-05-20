import io
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import magic
import msgspec

from chuni_penguin.types import (
    Chart,
    ClearLamp,
    ComboLamp,
    Difficulty,
    Judgements,
    PersonalBest,
    Profile,
    Rank,
    RatingSystem,
    RatingType,
    RecentScore,
    Score,
    SkillClass,
    Song,
)
from chuni_penguin.utils import floor_to_ndp

from .types import (
    KTBatchManualChunithm,
    KTBatchManualChunithmScore,
    KTChunithmChart,
    KTChunithmClass,
    KTChunithmClearLamp,
    KTChunithmJudgements,
    KTChunithmNoteLamp,
    KTChunithmOptionalData,
    KTChunithmPersonalBest,
    KTChunithmPersonalBestsResponseBody,
    KTChunithmScore,
    KTChunithmScoreResponseBody,
    KTChunithmUserProfile,
)

KT_CLEAR_LAMP_MAP: dict[KTChunithmClearLamp, ClearLamp] = {
    "CATASTROPHY": ClearLamp.catastrophy,
    "ABSOLUTE": ClearLamp.absolute,
    "BRAVE": ClearLamp.brave,
    "HARD": ClearLamp.hard,
    "CLEAR": ClearLamp.clear,
    "FAILED": ClearLamp.failed,
}
KT_REVERSE_CLEAR_LAMP_MAP: dict[ClearLamp, KTChunithmClearLamp] = {
    v: k for k, v in KT_CLEAR_LAMP_MAP.items()
}

KT_NOTE_LAMP_MAP: dict[KTChunithmNoteLamp, ComboLamp] = {
    "ALL JUSTICE CRITICAL": ComboLamp.all_justice_critical,
    "ALL JUSTICE": ComboLamp.all_justice,
    "FULL COMBO": ComboLamp.full_combo,
    "NONE": ComboLamp.none,
}
KT_REVERSE_NOTE_LAMP_MAP: dict[ComboLamp, KTChunithmNoteLamp] = {
    v: k for k, v in KT_NOTE_LAMP_MAP.items()
}


def convert_kt_to_score(
    score: KTChunithmScore | KTChunithmPersonalBest,
    song_title: str,
    chart: KTChunithmChart,
):
    judgements = score.score_data.judgements
    song = Song(id=chart.data.in_game_id, title=song_title)
    song_version = chart.data.display_version

    if song_version not in ("CHUNITHM", "CHUNITHM PLUS"):
        song_version = song_version.removeprefix("CHUNITHM ")

    song.version = song_version

    # WE charts use the difficulty field for storing the level, since difficulty must
    # be unique across all charts of a Tachi song.
    if chart.data.in_game_id >= 8000:
        bot_chart = Chart(
            difficulty=Difficulty.worlds_end,
            level=chart.difficulty,
            internal_level=None,
        )
    else:
        bot_chart = Chart(
            difficulty=getattr(Difficulty, chart.difficulty.lower()),
            level=chart.level,
            internal_level=chart.level_num,
        )

    record = Score(
        song=song,
        chart=bot_chart,
        score=score.score_data.score,
        rank=getattr(Rank, score.score_data.grade.lower().replace("+", "p")),
        clear_lamp=KT_CLEAR_LAMP_MAP.get(score.score_data.clear_lamp, ClearLamp.failed),
        combo_lamp=KT_NOTE_LAMP_MAP.get(score.score_data.note_lamp, ComboLamp.none),
        max_combo=score.score_data.optional.max_combo,
        rating=floor_to_ndp(Decimal(str(score.calculated_data.rating)), 2),
    )

    if score.time_achieved:
        record.achieved_at = datetime.fromtimestamp(score.time_achieved / 1000, tz=UTC)

    if (
        judgements.jcrit is not None
        and judgements.justice is not None
        and judgements.attack is not None
        and judgements.miss is not None
    ):
        record.judgements = Judgements(
            justice_critical=judgements.jcrit,
            justice=judgements.justice,
            attack=judgements.attack,
            miss=judgements.miss,
        )

    return record


def convert_kt_pbs_to_records(
    raw_body: Any | KTChunithmPersonalBestsResponseBody,
) -> list[PersonalBest]:
    if isinstance(raw_body, KTChunithmPersonalBestsResponseBody):
        body = raw_body
    else:
        body = msgspec.convert(raw_body, KTChunithmPersonalBestsResponseBody)

    charts_by_id = {c.id: c for c in body.charts}
    records: list[PersonalBest] = []

    for pb in body.pbs:
        chart = charts_by_id[pb.chart_id]

        records.append(
            PersonalBest.from_score(convert_kt_to_score(pb, chart.song.title, chart))
        )

    return records


def convert_kt_scores_to_records(
    raw_body: Any | KTChunithmScoreResponseBody,
) -> list[RecentScore]:
    if isinstance(raw_body, KTChunithmScoreResponseBody):
        body = raw_body
    else:
        body = msgspec.convert(raw_body, KTChunithmScoreResponseBody)

    charts_by_id = {c.id: c for c in body.charts}
    scores: list[RecentScore] = []

    for score in body.scores:
        chart = charts_by_id[score.chart_id]

        scores.append(
            RecentScore.from_score(convert_kt_to_score(score, chart.song.title, chart))
        )

    return scores


def convert_to_kt_batch_manual(profile: Profile, scores: Sequence[Score]):
    batch_manual = KTBatchManualChunithm()

    if profile.medal is not None:
        batch_manual.classes.dan = KTChunithmClass.from_skill_class(profile.medal)
    if profile.emblem is not None:
        batch_manual.classes.emblem = KTChunithmClass.from_skill_class(profile.emblem)

    for score in scores:
        tachi_score = KTBatchManualChunithmScore(
            score=score.score,
            note_lamp=KT_REVERSE_NOTE_LAMP_MAP.get(score.combo_lamp, "NONE"),
            clear_lamp=KT_REVERSE_CLEAR_LAMP_MAP.get(score.clear_lamp, "FAILED"),
            match_type="inGameID",
            identifier=str(score.song.id),
            difficulty=str(score.chart.difficulty),  # pyright: ignore[reportArgumentType]
        )

        if score.chart.difficulty == Difficulty.worlds_end:
            tachi_score.match_type = "gcmInGameIDSpecialChart"
            tachi_score.difficulty = msgspec.UNSET

        if score.achieved_at is not None:
            tachi_score.time_achieved = int(score.achieved_at.timestamp() * 1000)

        if score.judgements is not None:
            tachi_score.judgements = KTChunithmJudgements(
                jcrit=score.judgements.justice_critical,
                justice=score.judgements.justice,
                attack=score.judgements.attack,
                miss=score.judgements.miss,
            )

        if score.max_combo is not None:
            tachi_score.optional = KTChunithmOptionalData(max_combo=score.max_combo)

        batch_manual.scores.append(tachi_score)

    return batch_manual


def update_profile_from_ugpt_data(
    profile: Profile, ugpt_data: KTChunithmUserProfile
) -> Profile:
    profile.rating_systems = [
        RatingSystem(
            type=RatingType.naive,
            value=ugpt_data.game_stats.ratings.naive_rating,
        )
    ]
    profile.total_scores = ugpt_data.total_scores
    profile.extras = {
        "Session Playtime": f"{(ugpt_data.playtime) // (60 * 60 * 1000)} hours",
    }

    if (dan := ugpt_data.game_stats.classes.dan) is not msgspec.UNSET:
        profile.medal = getattr(SkillClass, dan.removeprefix("DAN_").lower())

    if (emblem := ugpt_data.game_stats.classes.emblem) is not msgspec.UNSET:
        profile.emblem = getattr(SkillClass, emblem.removeprefix("DAN_").lower())

    if (most_recent_score := ugpt_data.most_recent_score) is not None:
        profile.last_played = datetime.fromtimestamp(
            (most_recent_score.time_achieved or most_recent_score.time_added) / 1000,
            tz=UTC,
        )

    return profile


async def guess_mime_type(response: httpx.Response) -> str:
    data = io.BytesIO()

    async for chunk in response.aiter_bytes():
        if data.tell() == 0:
            # some simple and common formats can be checked first without
            # calling into libmagic
            fourcc = chunk[:4]

            if fourcc == b"GIF8":
                return "image/gif"

            if fourcc == b"\x89PNG":
                return "image/png"

            if fourcc[:3] == b"\xff\xd8\xff" and fourcc[3] in (0xDB, 0xE0, 0xE1, 0xEE):
                return "image/jpeg"

            if fourcc == b"RIFF" and fourcc[8:12] == b"WEBP":
                return "image/webp"

        data.write(chunk)

        if data.tell() >= 2048:
            break

    return magic.from_buffer(data.getvalue(), mime=True)
