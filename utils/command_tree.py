import asyncio
import binascii
import struct
from typing import TYPE_CHECKING, override

import discord
import msgspec
from discord.app_commands import CommandTree

if TYPE_CHECKING:
    from bot import ChuniBot


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

        if interaction.user.id in interaction.client.denylist:
            return False

        if (  # noqa: SIM103
            interaction.guild_id is not None
            and interaction.guild_id in interaction.client.denylist
        ):
            return False

        return True
