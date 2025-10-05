import asyncio
import contextvars
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

import discord
from discord.app_commands import locale_str
from discord.ext import commands
from discord.utils import MISSING
from fluent.runtime import FluentBundle, FluentLocalization, FluentResourceLoader
from fluent.runtime.resolver import Message

from chuni_penguin.context import PenguinContext
from utils.config import config

if TYPE_CHECKING:
    from bot import ChuniBot

TRANSLATIONS_DIR = Path(__file__).parent.parent / "i18n"
TRANSLATION_RESOURCES = ["main.ftl", "help.ftl"]

current_prefix: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_prefix", default=config.bot.default_prefix
)


class PenguinLocalization(FluentLocalization):
    """
    A subclass of FluentLocalization that allows accessing attributes using dot
    notation. Eagerly loads bundles in a serparate thread when awaited.
    """

    def load_bundles(self):
        for _ in self._bundles():
            pass

    def __await__(self):
        yield from asyncio.to_thread(self.load_bundles).__await__()
        return self

    def get_message(self, msg_id: str) -> tuple[Message, FluentBundle] | None:
        for bundle in self._bundles():
            if bundle.has_message(msg_id):
                return (bundle.get_message(msg_id), bundle)

        return None

    @override
    def format_value(self, msg_id: str, args: dict[str, Any] | None = None) -> str:
        base_msg_id, _, attribute_name = msg_id.partition(".")

        for bundle in self._bundles():
            if not bundle.has_message(base_msg_id):
                continue

            message = bundle.get_message(base_msg_id)
            value = message.value

            if attribute_name:
                value = message.attributes[attribute_name]

            if not value:
                continue

            val, _errors = bundle.format_pattern(value, args)

            assert isinstance(val, str)

            return val

        return msg_id


class FluentTranslator(discord.app_commands.Translator):
    def __init__(self) -> None:
        self._available_languages: list[str] = []
        self._fluent_loader: FluentResourceLoader = MISSING
        self._fluent_cache: dict[str, PenguinLocalization] = {}

    def _format_command(self, command: str) -> str:
        return f"{current_prefix.get()}{command}"

    def _load_localization(self, language_code: str):
        if language_code not in self._available_languages:
            return None

        return self._fluent_cache[language_code]

    async def load(self) -> None:
        self._available_languages = ["en-US", "en-GB"]
        self._fluent_loader = FluentResourceLoader(str(TRANSLATIONS_DIR / "{locale}"))

        self._fluent_cache["en-GB"] = self._fluent_cache[
            "en-US"
        ] = await PenguinLocalization(
            ["en-US"],
            TRANSLATION_RESOURCES,
            self._fluent_loader,
            functions={"COMMAND": self._format_command},  # pyright: ignore[reportArgumentType]
        )

        for language in TRANSLATIONS_DIR.iterdir():
            if language.name in ("en-US", "en-GB"):
                continue

            self._available_languages.append(language.name)
            self._fluent_cache[language.name] = await PenguinLocalization(
                [language.name, "en-US"],
                TRANSLATION_RESOURCES,
                self._fluent_loader,
                functions={"COMMAND": self._format_command},  # pyright: ignore[reportArgumentType]
            )

    async def translate(
        self,
        string: locale_str,
        locale: discord.Locale,
        context: discord.app_commands.TranslationContextTypes,
    ) -> str | None:
        localization = self._load_localization(locale.language_code)

        if localization is None:
            return None

        msgid = string.extras.pop("id", string.message)

        return localization.format_value(msgid, {"context": context, **string.extras})

    async def unload(self) -> None:
        self._available_languages.clear()
        self._fluent_loader = MISSING
        self._fluent_cache.clear()


class Internationalization(commands.Cog):
    def __init__(self, bot: "ChuniBot"):
        self.bot: "ChuniBot" = bot
        self.translator: FluentTranslator = FluentTranslator()

    @override
    async def cog_load(self) -> None:
        await self.bot.tree.set_translator(self.translator)

    @override
    async def cog_unload(self) -> None:
        await self.bot.tree.set_translator(None)

    @commands.Cog.listener()
    async def on_command(self, ctx: PenguinContext):
        current_prefix.set(ctx.clean_prefix)


async def setup(bot: "ChuniBot"):
    await bot.add_cog(Internationalization(bot))


async def teardown(bot: "ChuniBot"):
    await bot.remove_cog("Internationalization")
