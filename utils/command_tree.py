import asyncio
import struct
import zlib

import msgspec
from discord.app_commands import CommandTree


class VersionableCommandTree(CommandTree):
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

        unsigned_hash = zlib.crc32(msgspec.msgpack.encode(payload))
        return struct.unpack("<i", struct.pack("<I", unsigned_hash))[0]
