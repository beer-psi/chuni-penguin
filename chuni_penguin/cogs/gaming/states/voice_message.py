import secrets
from typing import TYPE_CHECKING, override

import discord
from discord.http import handle_message_parameters

from chuni_penguin.oggopus import generate_waveform
from chuni_penguin.utils import json_dumps, json_loads

from .base import GuessingGameState
from .wait_for_answer import WaitForAnswerState

if TYPE_CHECKING:
    from chuni_penguin.cogs.gaming._session import GuessingGameSession


class AskVoiceMessageQuestionState(GuessingGameState):
    def __init__(self, session: "GuessingGameSession") -> None:
        self.session: "GuessingGameSession" = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        (
            song,
            aliases,
            audio_buffer,
            jacket_art,
        ) = await self.session.get_voice_message_question()

        question_embed = discord.Embed(
            title="Guess the song!",
            description=f"You have {self.session.time_per_question} seconds to guess the song.\nUse `{self.session.ctx.clean_prefix}skip` to skip.",
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

        with handle_message_parameters(
            file=discord.File(audio_buffer, filename="question.ogg"),
            nonce=secrets.randbits(64),
            flags=discord.MessageFlags(voice=True),
        ) as params:
            assert params.multipart is not None

            payload_json_part = next(
                x for x in params.multipart if x["name"] == "payload_json"
            )
            payload = json_loads(payload_json_part["value"])
            payload["attachments"][0]["duration_secs"] = self.session.get_audio_length()
            payload["attachments"][0]["waveform"] = generate_waveform(
                audio_buffer, self.session.get_audio_length()
            )
            payload_json_part["value"] = json_dumps(payload)

            file_0_part = next(x for x in params.multipart if x["name"] == "files[0]")
            file_0_part["content_type"] = "audio/ogg"

            await self.session.channel.send(embed=question_embed)
            await self.session.bot.http.send_message(
                self.session.channel.id, params=params
            )

        audio_buffer.close()

        return WaitForAnswerState(
            self.session, song=song, aliases=aliases, answer_image=jacket_art
        )
