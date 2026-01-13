import asyncio
import binascii
import struct
from typing import TYPE_CHECKING, override

import discord
import msgspec
from discord.app_commands import CommandTree

from chuni_penguin.config import config
from chuni_penguin.database import Denylist
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
        if await interaction.client.is_owner(interaction.user):
            return True

        ban_entry: Denylist | None = None
        server_name: str | None = None

        if interaction.user.id in interaction.client.denylist:
            ban_entry = interaction.client.denylist[interaction.user.id]
        elif (
            interaction.guild is not None
            and interaction.guild.id in interaction.client.denylist
        ):
            ban_entry = interaction.client.denylist[interaction.guild.id]
            server_name = interaction.guild.name

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
