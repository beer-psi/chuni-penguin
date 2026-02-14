import asyncio
import re
from typing import TYPE_CHECKING, Any, Literal, Sequence, cast, override

import discord
from discord.ext import songbird
from discord.utils import escape_markdown
from sqlalchemy import Row, desc, func, select

from chuni_penguin.cogs.gaming._session import GuessingGameSession, GuessingGameType
from chuni_penguin.config import config
from chuni_penguin.context import PenguinGuildContext
from chuni_penguin.converters import Level, LevelRange, LevelRangeConverter
from chuni_penguin.database import GuessScore
from chuni_penguin.networks.types import Difficulty, Genre

from ._pagination import ListPageSource, PaginationView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot
    from chuni_penguin.cogs.gaming import GamingCog


class GuessLeaderboardPageSource(ListPageSource[Difficulty | None]):
    __slots__ = ("bot", "game_type", "guild_id", "guild_name", "leaderboard_type")

    def __init__(self, bot: "ChuniBot", guild_id: int, guild_name: str) -> None:
        super().__init__(
            [
                None,
                Difficulty.basic,
                Difficulty.advanced,
                Difficulty.expert,
                Difficulty.master,
                Difficulty.ultima,
            ],
            per_page=1,
        )
        self.bot = bot
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.game_type: GuessingGameType | None = None
        self.leaderboard_type: Literal["server", "global"] = "server"

    @override
    async def get_page(self, page_index: int) -> Sequence[Row[tuple[int, int]]]:  # pyright: ignore[reportIncompatibleMethodOverride]
        difficulty = self.entries[page_index]

        async with self.bot.begin_db_session() as session:
            if difficulty is not None and self.game_type is not None:
                stmt = (
                    select(
                        GuessScore.discord_id.label("discord_id"),
                        GuessScore.score.label("score"),
                    )
                    .where(
                        (GuessScore.difficulty == difficulty.value)
                        & (GuessScore.game_type == self.game_type.value)
                    )
                    .order_by(desc("score"))
                    .limit(10)
                )

                if self.leaderboard_type == "server":
                    stmt = stmt.where(GuessScore.guild_id == self.guild_id)
            else:
                stmt = select(
                    GuessScore.discord_id.label("discord_id"),
                    func.sum(GuessScore.score).label("score"),
                )

                if self.leaderboard_type == "server":
                    stmt = stmt.where(GuessScore.guild_id == self.guild_id)

                if difficulty is not None:
                    stmt = stmt.where(GuessScore.difficulty == difficulty.value)
                elif self.game_type is not None:
                    stmt = stmt.where(GuessScore.game_type == self.game_type.value)

                stmt = (
                    stmt.order_by(desc("score"))
                    .group_by(GuessScore.discord_id)
                    .limit(10)
                )

            return (await session.execute(stmt)).fetchall()

    @override
    async def format_page(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, menu: "PaginationView", page: Sequence[Row[tuple[int, int]]]
    ) -> dict[str, Any]:
        description = ""
        difficulty = self.entries[menu.current_page]

        if self.leaderboard_type == "server":
            title = f"Guess Leaderboard for {escape_markdown(self.guild_name)}"
        else:
            title = "Global Guess Leaderboard"

        if difficulty is not None:
            title += f" [{difficulty}]"

        for idx, score in enumerate(page):
            description += f"\u200b{idx + 1}. <@{score[0]}>: {score[1]}\n"

        embed = discord.Embed(
            color=discord.Color.yellow() if difficulty is None else difficulty.color(),
            title=title,
            description=description,
        )

        return {"embed": embed}


class GuessLeaderboardView(PaginationView):
    def __init__(self, ctx: PenguinGuildContext):
        # since the super `self.source` is just a PageSourceProtocol, and we want
        # typed access to the actual source without ugly casting
        self._source = GuessLeaderboardPageSource(ctx.bot, ctx.guild.id, ctx.guild.name)

        super().__init__(ctx, self._source)
        self.add_item(self.game_type_all)
        self.add_item(self.game_type_image)
        self.add_item(self.game_type_audio)
        self.add_item(self.game_type_voice)
        self.add_item(self.leaderboard_type_server)
        self.add_item(self.leaderboard_type_global)

    @override
    async def on_timeout(self) -> None:
        self.game_type_all.disabled = True
        self.game_type_image.disabled = True
        self.game_type_audio.disabled = True
        self.game_type_voice.disabled = True
        self.leaderboard_type_server.disabled = True
        self.leaderboard_type_global.disabled = True

        self.remove_item(self.to_first_page)
        self.remove_item(self.to_previous_page)
        self.remove_item(self.jump_to_page)
        self.remove_item(self.to_next_page)
        self.remove_item(self.to_last_page)

        if self.message is not None:
            await self.message.edit(view=self)

    @discord.ui.button(label="All", row=2, style=discord.ButtonStyle.green)
    async def game_type_all(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_game_type(interaction, button, None)

    @discord.ui.button(label=GuessingGameType.IMAGE.value, row=2)
    async def game_type_image(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_game_type(interaction, button, GuessingGameType.IMAGE)

    @discord.ui.button(label=GuessingGameType.VOICE_MESSAGE.value, row=2)
    async def game_type_audio(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_game_type(
            interaction, button, GuessingGameType.VOICE_MESSAGE
        )

    @discord.ui.button(label=GuessingGameType.VOICE_CHANNEL.value, row=2)
    async def game_type_voice(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_game_type(
            interaction, button, GuessingGameType.VOICE_CHANNEL
        )

    @discord.ui.button(label="Server", row=3, style=discord.ButtonStyle.green)
    async def leaderboard_type_server(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_leaderboard_type(interaction, button, "server")

    @discord.ui.button(label="Global", row=3)
    async def leaderboard_type_global(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_leaderboard_type(interaction, button, "global")

    async def _switch_game_type(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
        game_type: GuessingGameType | None,
    ):
        await interaction.response.defer()

        self._source.game_type = game_type

        self.game_type_all.style = discord.ButtonStyle.secondary
        self.game_type_image.style = discord.ButtonStyle.secondary
        self.game_type_audio.style = discord.ButtonStyle.secondary
        self.game_type_voice.style = discord.ButtonStyle.secondary

        button.style = discord.ButtonStyle.green

        await self.show_page(interaction, self.current_page)

    async def _switch_leaderboard_type(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
        leaderboard_type: Literal["server", "global"],
    ):
        await interaction.response.defer()

        self._source.leaderboard_type = leaderboard_type

        self.leaderboard_type_global.style = discord.ButtonStyle.secondary
        self.leaderboard_type_server.style = discord.ButtonStyle.secondary

        button.style = discord.ButtonStyle.green

        await self.show_page(interaction, self.current_page)


class RetryGameButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"retryguess(?P<mode>[012]):(?P<difficulty>\d+):(?P<questions>\d+):(?P<score>\d*):(?P<time>\d+):(?P<wrong>\d*):(?P<hardcore>[01]):(?P<genres>[\d,]*)(?::(?P<volume>\d+))?(?::(?P<levels>[\d\-+.,]*))?(?::(?P<seed>[A-NP-Z1-9]{8})?)?",
):
    def __init__(
        self,
        *,
        mode: GuessingGameType,
        difficulty: Difficulty,
        questions: int,
        score: int | None,
        time: int,
        wrong: int | None,
        hardcore: bool,
        genres: list[Genre] | None,
        levels: list[Level | LevelRange] | None,
        volume: int,
        seed: str | None = None,
        row: int | None = None,
    ) -> None:
        if mode == GuessingGameType.IMAGE:
            mode_id = "0"
        elif mode == GuessingGameType.VOICE_MESSAGE:
            mode_id = "1"
        elif mode == GuessingGameType.VOICE_CHANNEL:
            mode_id = "2"
        else:
            msg = f"Unknown guess game mode: {mode}"
            raise ValueError(msg)

        custom_id_parts: list[str] = [
            mode_id,
            str(difficulty.value),
            str(questions),
            str(score) if score is not None else "",
            str(time),
            str(wrong) if wrong is not None else "",
            "1" if hardcore else "0",
            ",".join([str(g.value) for g in genres]) if genres else "",
            str(volume),
            ",".join([str(level) for level in levels]) if levels else "",
            seed if seed is not None else "",
        ]

        super().__init__(
            discord.ui.Button(
                style=(
                    discord.ButtonStyle.green
                    if seed is None
                    else discord.ButtonStyle.secondary
                ),
                label="Retry" if seed is None else "Retry (same seed)",
                custom_id=f"retryguess{':'.join(custom_id_parts)}",
            ),
            row=row,
        )

        self.mode = mode
        self.difficulty = difficulty
        self.questions = questions
        self.score = score
        self.time = time
        self.wrong = wrong
        self.hardcore = hardcore
        self.genres = genres
        self.volume = volume
        self.levels = levels
        self.seed = seed

    @classmethod
    async def from_custom_id(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ):
        if match["mode"] == "0":
            mode = GuessingGameType.IMAGE
        elif match["mode"] == "1":
            mode = GuessingGameType.VOICE_MESSAGE
        elif match["mode"] == "2":
            mode = GuessingGameType.VOICE_CHANNEL
        else:
            msg = f"Unknown guess mode ID: {match['mode']}"
            raise ValueError(msg)

        difficulty = Difficulty(int(match["difficulty"]))
        questions = int(match["questions"])
        score = int(match["score"]) if match["score"] else None
        time = int(match["time"])
        wrong = int(match["wrong"]) if match["wrong"] else None
        hardcore = match["hardcore"] == "1"
        genres = (
            [Genre(int(x)) for x in match["genres"].split(",")]
            if match["genres"]
            else None
        )
        volume = int(match["volume"]) if match["volume"] else 15

        level_range_converter = LevelRangeConverter()
        levels = (
            await asyncio.gather(
                *[
                    # This doesn't actually need a context object, that's just how the
                    # converter interface goes.
                    level_range_converter.convert(None, level)  # pyright: ignore[reportArgumentType]
                    for level in match["levels"].split(",")
                ]
            )
            if match["levels"]
            else None
        )
        seed = match["seed"]

        return cls(
            mode=mode,
            difficulty=difficulty,
            questions=questions,
            score=score,
            time=time,
            wrong=wrong,
            hardcore=hardcore,
            genres=genres,
            volume=volume,
            levels=levels,
            seed=seed,
        )

    @override
    async def callback(self, interaction: discord.Interaction["ChuniBot"]) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        gaming = cast("GamingCog | None", interaction.client.get_cog("Games"))

        if gaming is None:
            await interaction.response.send_message(
                "Games aren't currently available. Sorry about that!", ephemeral=True
            )
            return

        if gaming.shutting_down:
            await interaction.response.send_message(
                "I am currently pending a restart. No new games can be started. Please wait a few minutes.",
                ephemeral=True,
            )
            return

        if (
            interaction.channel_id is None
            or interaction.channel is None
            or interaction.message is None
        ):
            await interaction.response.send_message(
                "Could not retrieve required information to start the game.",
                ephemeral=True,
            )
            return

        async with gaming.game_sessions.read() as game_sessions:
            if interaction.channel_id in game_sessions:
                await interaction.response.send_message(
                    "There is already an ongoing session in this channel.",
                    ephemeral=True,
                )
                return

        if self.mode == GuessingGameType.VOICE_CHANNEL:
            if interaction.guild is None or not isinstance(
                interaction.user, discord.Member
            ):
                await interaction.response.send_message(
                    f"Cannot start a {self.mode.value} game outside of servers.",
                    ephemeral=True,
                )
                return

            if interaction.guild.voice_client is not None:
                await interaction.response.send_message(
                    "Another voice guessing game is already ongoing in this server. Only one voice guessing game can run at a time for each server.",
                    ephemeral=True,
                )
                return

            if interaction.user.voice is None or interaction.user.voice.channel is None:
                await interaction.response.send_message(
                    f"You must connect to a voice channel to start a {self.mode} guessing game.",
                    ephemeral=True,
                )
                return

            await interaction.user.voice.channel.connect(
                cls=songbird.SongbirdClient, self_deaf=True
            )

        ctx = await interaction.client.get_context(interaction.message)
        # user will have the appropriate type if the message is in a guild context
        ctx.author = interaction.user  # pyright: ignore[reportAttributeAccessIssue]
        ctx.prefix = (
            interaction.client.prefixes.get(
                interaction.guild_id, config.bot.default_prefix
            )
            if interaction.guild_id is not None
            else config.bot.default_prefix
        )

        async with gaming.game_sessions.write() as game_sessions:
            session = game_sessions[interaction.channel_id] = GuessingGameSession(
                ctx,
                difficulty=self.difficulty,
                game_type=self.mode,
                question_count=self.questions,
                score_limit=self.score,
                time_per_question=self.time,
                wrong_answers_limit=self.wrong,
                hardcore_mode=self.hardcore,
                genres=self.genres,
                volume=self.volume,
                levels=self.levels,
                seed=self.seed,
            )

        voice_channel_id = (
            interaction.guild.voice_client.channel.id
            if interaction.guild is not None
            and isinstance(interaction.guild.voice_client, songbird.SongbirdClient)
            else None
        )

        async def after(e):
            await gaming._clear_state(interaction.channel_id)  # pyright: ignore[reportArgumentType]

            if voice_channel_id is not None:
                await gaming._clear_state(voice_channel_id)

        game_task = asyncio.create_task(
            session.run(after=after),
            name=f"chuni-penguin-guess-{interaction.channel_id}",
        )

        gaming.game_tasks.add(game_task)
        game_task.add_done_callback(gaming.game_tasks.discard)

        await interaction.response.send_message("New game started.", ephemeral=True)
