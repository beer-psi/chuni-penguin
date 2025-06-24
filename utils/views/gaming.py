import asyncio
import re
from typing import TYPE_CHECKING, Any, Sequence, cast, override

import discord
from discord.ext.commands import Context
from discord.utils import escape_markdown
from sqlalchemy import Row, desc, func, select

from chunithm_net.models.enums import Difficulty, Genres
from cogs.gaming._session import GuessingGameSession, GuessingGameType
from cogs.gaming.states.start import StartState
from database.models import GuessScore
from utils.config import config

from ._pagination import ListPageSource, PaginationView

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.gaming import GamingCog


class GuessLeaderboardPageSource(ListPageSource[Difficulty | None]):
    def __init__(self, bot: "ChuniBot", guild_id: int, guild_name: str) -> None:
        super().__init__(
            [
                None,
                Difficulty.BASIC,
                Difficulty.ADVANCED,
                Difficulty.EXPERT,
                Difficulty.MASTER,
                Difficulty.ULTIMA,
            ],
            per_page=1,
        )
        self.bot = bot
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.game_type: GuessingGameType | None = None

    @override
    async def get_page(self, page_number: int) -> Sequence[Row[tuple[int, int]]]:  # pyright: ignore[reportIncompatibleMethodOverride]
        difficulty = self.entries[page_number]

        async with self.bot.begin_db_session() as session:
            if difficulty is not None and self.game_type is not None:
                stmt = (
                    select(
                        GuessScore.discord_id.label("discord_id"),
                        GuessScore.score.label("score"),
                    )
                    .where(
                        (GuessScore.guild_id == self.guild_id)
                        & (GuessScore.difficulty == difficulty.value)
                        & (GuessScore.game_type == self.game_type.value)
                    )
                    .order_by(desc("score"))
                    .limit(10)
                )
            else:
                stmt = select(
                    GuessScore.discord_id.label("discord_id"),
                    func.sum(GuessScore.score).label("score"),
                ).where(GuessScore.guild_id == self.guild_id)

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

        title = f"Guess Leaderboard for {escape_markdown(self.guild_name)}"

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
    def __init__(self, ctx: Context):
        assert ctx.guild is not None

        # since the super `self.source` is just a PageSourceProtocol, and we want
        # typed access to the actual source without ugly casting
        self._source = GuessLeaderboardPageSource(ctx.bot, ctx.guild.id, ctx.guild.name)

        super().__init__(ctx, self._source)
        self.add_item(self.game_type_all)
        self.add_item(self.game_type_image)
        self.add_item(self.game_type_audio)
        self.add_item(self.game_type_voice)

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


class RetryGameButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"retryguess(?P<mode>[012]):(?P<difficulty>\d+):(?P<questions>\d+):(?P<score>\d*):(?P<time>\d+):(?P<wrong>\d*):(?P<hardcore>[01]):(?P<genres>[\d,]*)",
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
        genres: list[Genres] | None,
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

        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.green,
                label="Retry",
                custom_id=f"retryguess{mode_id}:{difficulty.value}:{questions}:{score if score is not None else ''}:{time}:{wrong if wrong is not None else ''}:{'1' if hardcore else '0'}:{','.join([str(g.value) for g in genres]) if genres else ''}",
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
            [Genres(int(x)) for x in match["genres"].split(",")]
            if match["genres"]
            else None
        )

        return cls(
            mode=mode,
            difficulty=difficulty,
            questions=questions,
            score=score,
            time=time,
            wrong=wrong,
            hardcore=hardcore,
            genres=genres,
        )

    @override
    async def callback(self, interaction: discord.Interaction["ChuniBot"]) -> Any:
        gaming = cast("GamingCog | None", interaction.client.get_cog("Games"))

        if gaming is None:
            await interaction.response.send_message(
                "Games aren't currently available. Sorry about that!", ephemeral=True
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

        if interaction.channel_id in gaming.game_sessions:
            await interaction.response.send_message(
                "There is already an ongoing session in this channel.", ephemeral=True
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

            await interaction.user.voice.channel.connect(self_deaf=True)

        ctx = await interaction.client.get_context(interaction.message)
        ctx.author = interaction.user
        ctx.prefix = (
            interaction.client.prefixes.get(
                interaction.guild_id, config.bot.default_prefix
            )
            if interaction.guild_id is not None
            else config.bot.default_prefix
        )

        async with gaming.game_sessions_lock:
            session = gaming.game_sessions[interaction.channel_id] = (
                GuessingGameSession(
                    ctx,
                    difficulty=self.difficulty,
                    game_type=self.mode,
                    question_count=self.questions,
                    score_limit=self.score,
                    time_per_question=self.time,
                    wrong_answers_limit=self.wrong,
                    hardcore_mode=self.hardcore,
                    genres=self.genres,
                )
            )

        from cogs.gaming import run_state_machine

        game_task = asyncio.create_task(
            run_state_machine(gaming, session.ctx.channel, session, StartState(session))
        )

        gaming.game_tasks.add(game_task)
        game_task.add_done_callback(gaming.game_tasks.discard)

        await interaction.response.send_message("New game started.", ephemeral=True)
