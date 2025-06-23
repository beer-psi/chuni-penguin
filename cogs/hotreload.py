import os
import pathlib

from discord.ext import commands, tasks

from cogs import COG_LIST
from utils.logging import logger

# put your extension names in this list
# if you don't want them to be reloaded
IGNORE_EXTENSIONS: list[str] = ["jishaku"]


def path_from_extension(extension: str) -> pathlib.Path:
    path = pathlib.Path(extension.replace(".", os.sep) + ".py")

    if not path.exists():
        path = pathlib.Path(extension.replace(".", os.sep)) / "__init__.py"

    return path


class HotReload(commands.Cog):
    """
    Cog for reloading extensions as soon as the file is edited
    """

    def __init__(self, bot):
        self.bot = bot
        self.hot_reload_loop.start()
        self.last_modified_time: dict[str, float] = {}

    async def cog_unload(self):
        self.hot_reload_loop.stop()

    @tasks.loop(seconds=3)
    async def hot_reload_loop(self):
        for extension in COG_LIST:
            if extension in IGNORE_EXTENSIONS:
                continue

            path = path_from_extension(extension)
            new_lmt = path.stat().st_mtime
            old_lmt = self.last_modified_time.get(extension)

            if old_lmt is not None and old_lmt == new_lmt:
                continue

            self.last_modified_time[extension] = new_lmt

            try:
                # For d.py 2.0, await the next line
                await self.bot.reload_extension(extension)
            except commands.ExtensionError as e:
                await logger.aerror(
                    "Couldn't reload extension",
                    tag="extension_error",
                    extension=extension,
                    exc_info=e,
                )
            else:
                await logger.ainfo(
                    "Reloaded extension", tag="reload_extension", extension=extension
                )
            finally:
                self.last_modified_time[extension] = new_lmt

    @hot_reload_loop.before_loop
    async def cache_last_modified_time(self):
        self.last_modified_time = {}
        # Mapping = {extension: timestamp}
        for extension in self.bot.extensions:
            if extension in IGNORE_EXTENSIONS:
                continue
            path = path_from_extension(extension)
            lmt = path.stat().st_mtime
            self.last_modified_time[extension] = lmt


async def setup(bot):
    cog = HotReload(bot)
    await bot.add_cog(cog)


# For d.py 2.0, comment the above setup function
# and uncomment the below
# async def setup(bot):
#     cog = HotReload(bot)
#     await bot.add_cog(cog)
