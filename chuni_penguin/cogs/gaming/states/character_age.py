from typing import TYPE_CHECKING

import discord
from discord.utils import escape_markdown

from chuni_penguin.config import config

from .base import GuessingGameState
from .wait_for_answer import WaitForCharacterAgeAnswerState

if TYPE_CHECKING:
    from chuni_penguin.cogs.gaming._session import GuessingGameSession


class AskCharacterAgeQuestionState(GuessingGameState):
    __slots__ = ("session",)

    def __init__(self, session: "GuessingGameSession") -> None:
        self.session = session

    async def __call__(self) -> "GuessingGameState | None":
        character = await self.session.get_character_question()
        question_embed = discord.Embed(
            color=discord.Color.yellow(),
            title="Guess the character's age!",
            description=(
                f"**{escape_markdown(character.name)}**\n"
                "\n"
                f"You have {self.session.time_per_question} seconds to guess the character's age.\n"
                f"Use `{self.session.ctx.clean_prefix}skip` to skip.\n"
                "Answers must be numbers. If a character is immortal, submit `inf`."
            ),
        )

        if config.web.is_accessible:
            question_embed.set_image(
                url=f"{config.web.base_url}/assets/characters/{character.id}.webp"
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

        return WaitForCharacterAgeAnswerState(self.session, character=character)
