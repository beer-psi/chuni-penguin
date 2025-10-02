import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, override

import discord
from discord.ext import songbird

from cogs.gaming.states.end_game import EndGameVoiceDisconnected

from .base import GuessingGameState
from .wait_for_answer import WaitForAnswerState

if TYPE_CHECKING:
    from cogs.gaming._session import GuessingGameSession


class AskVoiceCallQuestionState(GuessingGameState):
    def __init__(self, session: "GuessingGameSession") -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        # we should already be in a voice channel if we reach here, so voice_client should not
        # be null. if it's null, it's a bug.

        if self.session.voice_client is None:
            return EndGameVoiceDisconnected(self.session)

        assert self.session.voice_client.channel is not None

        (
            song,
            aliases,
            jacket_art,
            audio_path,
            audio_start,
            audio_length,
        ) = await self.session.get_voice_question()

        track = songbird.Track(songbird.File(str(audio_path)))
        track.pause()

        try:
            track_handle = await self.session.voice_client.play(track)
        except discord.ClientException:
            return EndGameVoiceDisconnected(self.session)

        await track_handle.make_playable()
        track_handle.set_volume(self.session.volume / 100)
        await track_handle.seek(timedelta(seconds=audio_start))

        question_embed = discord.Embed(
            title="Guess the song!",
            description=(
                f"You have {self.session.time_per_question} seconds to guess the song.\n"
                f"Use `{self.session.ctx.clean_prefix}skip` to skip.\n"
                f"The audio is being played in {self.session.voice_client.channel.mention}."
            ),
            color=self.session.difficulty.color(),
        )

        if self.session.question_count is not None:
            question_embed.set_footer(
                text=f"Question {self.session.questions_done + 1} / {self.session.question_count}"
            )
        else:
            question_embed.set_footer(
                text=f"Question {self.session.questions_done + 1}"
            )

        await self.session.channel.send(embed=question_embed, mention_author=False)
        track_handle.play()

        async def stop_music():
            await asyncio.sleep(audio_length)
            track_handle.stop()

        return WaitForAnswerState(
            self.session,
            song=song,
            aliases=aliases,
            answer_image=jacket_art,
            stop_music_task=asyncio.create_task(stop_music()),
        )
