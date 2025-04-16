import asyncio
import zlib

import msgspec
from discord.app_commands import CommandTree


class VersionableCommandTree(CommandTree):
    async def get_hash(self):
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

        return zlib.crc32(msgspec.msgpack.encode(payload))
