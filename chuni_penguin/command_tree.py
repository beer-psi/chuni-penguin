import asyncio
import binascii
import contextlib
import struct
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import discord
import msgspec
from discord.app_commands import CommandTree

from chuni_penguin.config import config
from chuni_penguin.logging import logger
from chuni_penguin.ui.components import BannedEmbed

if TYPE_CHECKING:
    from .bot import ChuniBot


class PenguinCommandTree(CommandTree["ChuniBot"]):
    async def get_hash(self) -> int:
        commands = sorted(
            self._get_all_commands(guild=None), key=lambda c: c.qualified_name
        )
        translator = self.translator

        if translator is not None:
            payload = await asyncio.gather(
                *[
                    command.get_translated_payload(self, translator)
                    for command in commands
                ]
            )
        else:
            payload = [command.to_dict(self) for command in commands]

        unsigned_hash = binascii.crc32(msgspec.msgpack.encode(payload))
        return struct.unpack("<i", struct.pack("<I", unsigned_hash))[0]

    @override
    async def interaction_check(
        self, interaction: discord.Interaction["ChuniBot"], /
    ) -> bool:
        delta = datetime.now(UTC) - interaction.created_at

        if delta.total_seconds() >= 2.8:
            await logger.awarning(
                "Ignoring interaction, running late.",
                tag="interaction_ignore_high_latency",
                interaction_id=interaction.id,
                latency=delta.total_seconds(),
            )
            return False

        if not interaction.client.is_ready():
            if interaction.type != discord.InteractionType.autocomplete:
                with contextlib.suppress(discord.NotFound):
                    await interaction.response.send_message(
                        "The bot is currently starting, please wait...", ephemeral=True
                    )

            return False

        if await interaction.client.is_owner(interaction.user):
            return True

        ban_entry, server_name = interaction.client.permissions.get_denylist_entry(
            interaction.user.id, interaction.guild
        )

        if ban_entry is not None:
            await interaction.response.send_message(
                embed=BannedEmbed(
                    client=interaction.client,
                    entry=ban_entry,
                    server_name=server_name,
                    support_server_invite=config.bot.support_server_invite,
                ),
                ephemeral=True,
            )
            return False

        return await interaction.client.permissions.permissions_interaction_check(
            interaction
        )
