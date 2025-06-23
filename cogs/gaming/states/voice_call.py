from typing import TYPE_CHECKING, override

import discord

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
        # be null. if it's null, it's a bug
        assert self.session.voice_client is not None
        assert self.session.voice_client.channel is not None

        (
            song,
            aliases,
            audio_buffer,
            jacket_art,
        ) = await self.session.get_voice_message_question()

        question_embed = discord.Embed(
            title="Guess the song!",
            description=(
                f"You have {self.session.time_per_question} seconds to guess the song.\n"
                f"Use `{self.session.ctx.prefix}skip` to skip.\n"
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

        # if you use the asset extraction scripts provided, audio should always be opus.
        self.session.voice_client.play(
            discord.FFmpegOpusAudio(audio_buffer, codec="copy", pipe=True),
            after=lambda _: audio_buffer.close(),
        )

        return WaitForAnswerState(
            self.session, song=song, aliases=aliases, answer_image=jacket_art
        )
