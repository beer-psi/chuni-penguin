import asyncio
import secrets
from typing import TYPE_CHECKING, override

import discord
from discord.http import handle_message_parameters

from utils import json_dumps, json_loads

from .base import GuessingGameState
from .wait_for_answer import WaitForAnswerState

if TYPE_CHECKING:
    from cogs.gaming._session import GuessingGameSession


class AskVoiceMessageQuestionState(GuessingGameState):
    def __init__(self, session: "GuessingGameSession") -> None:
        self.session: "GuessingGameSession" = session

        self._task: asyncio.Task | None = None

    @override
    async def __call__(self) -> "GuessingGameState | None":
        (
            song,
            aliases,
            audio_path,
            jacket_art,
        ) = await self.session.get_voice_message_question()

        question_embed = discord.Embed(
            title="Guess the song!",
            description=f"You have {self.session.time_per_question} seconds to guess the song.\nUse `{self.session.ctx.prefix}skip` to skip.",
            color=self.session.difficulty.color(),
        )
        await self.session.channel.send(embed=question_embed, mention_author=False)

        with handle_message_parameters(
            file=discord.File(audio_path, filename="question.ogg"),
            nonce=secrets.randbits(64),
            flags=discord.MessageFlags._from_value(8192),
        ) as params:
            assert params.multipart is not None

            payload_json_part = next(
                x for x in params.multipart if x["name"] == "payload_json"
            )
            payload = json_loads(payload_json_part["value"])
            payload["attachments"][0]["duration_secs"] = self.session.get_audio_length()
            payload["attachments"][0]["waveform"] = "AA=="
            payload_json_part["value"] = json_dumps(payload)

            file_0_part = next(x for x in params.multipart if x["name"] == "files[0]")
            file_0_part["content_type"] = "audio/ogg"

            await self.session.bot.http.send_message(
                self.session.channel.id, params=params
            )

        audio_path.unlink()

        return WaitForAnswerState(
            self.session, song=song, aliases=aliases, answer_image=jacket_art
        )
