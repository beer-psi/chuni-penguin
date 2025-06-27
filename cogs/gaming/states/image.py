from typing import override

import discord

from cogs.gaming._session import GuessingGameSession

from .base import GuessingGameState
from .wait_for_answer import WaitForAnswerState


class AskImageQuestionState(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        (
            song,
            aliases,
            answer_image,
            question_image,
        ) = await self.session.get_image_question()

        question_embed = discord.Embed(
            title="Guess the song!",
            description=f"You have {self.session.time_per_question} seconds to guess the song.\nUse `{self.session.ctx.clean_prefix}skip` to skip.",
            color=self.session.difficulty.color(),
        )
        question_embed.set_image(url="attachment://image.png")

        if self.session.question_count is not None:
            question_embed.set_footer(
                text=f"Question {self.session.questions_done + 1} / {self.session.question_count}"
            )
        else:
            question_embed.set_footer(
                text=f"Question {self.session.questions_done + 1}"
            )

        await self.session.channel.send(
            embed=question_embed,
            file=discord.File(question_image, "image.png"),
            mention_author=False,
        )
        question_image.close()

        return WaitForAnswerState(
            self.session, song=song, aliases=aliases, answer_image=answer_image
        )
