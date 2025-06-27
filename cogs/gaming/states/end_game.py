import random
from typing import override

import discord
from discord.utils import MISSING

from cogs.gaming._session import GuessingGameSession

from .base import GuessingGameState

# Tips that don't need any sort of session data.
STATIC_TIPS = tips = [
    "Your support is humbly requested. https://ko-fi.com/beerpsi_",
    "Don't like how this game works? Help improve it at https://github.com/beer-psi/chuni-penguin",
    "I sure hope the employer looking at this thinks I'm cool",
    "i'm chuning my shit",
    "WTF sperm slider",
    "TRUENITHM NUKE",
    "The bread you ate for lunch is farmable",
    "i can help you set this up for a symbolic $15 fee",
    "in my onion",
    "+0.5 overpower",
    "-0.5 overpower",
    "have you tried xl techno more dance remix its literally free rating hack. i got sss+ in 3 tries trust me bro its so free. easiest chart in the game just hit the notes its that simple",
    "question 1-5: clearly recognized the wrong song",
    "Announcement Regarding Chuni Penguin's Graduation",
    "ALL I WANNA DO / jaQup / 7 days a week",
    "people who are worse than me are garbage and people who are better than me need to get a life",
    "mirror IS cheating",
    "im an adult? ok bro, then like, date one....",
    "IS THAT ODIN BY GRAM",
    "do you want to buy a controller",
    "repost if you have dementia",
    "Tips Have The Right To Humour",
    "'DROP TABLE guess_leaderboard;--",
    "it's been one week since ya looked at me",
    "put the maid dress on",
    "you could be playing balatro right now",
    "Play UNREAL LIFE",
    "c>guess is actually the shittiest fucking minigame. Ugly ass UI, bot keeps rebooting, crops that are honestly impossible, the only people enjoying the game are 30 somethings who have played the game for 15 years",
    "go ahead, look up the source for these tips, ruin the fun for yourself",
]


async def end_game(
    session: GuessingGameSession,
    color: discord.Color,
    description: str,
    *,
    footer: str | None = None,
    show_lives: bool = True,
):
    from utils.views.gaming import RetryGameButton

    embed = discord.Embed(
        color=color,
        title="Game ended",
        description=description,
    )
    embed.add_field(name="Game type", value=session.game_type.value, inline=True)
    embed.add_field(name="Difficulty", value=str(session.difficulty))

    if show_lives and session.wrong_answers_limit:
        embed.add_field(name="LIFE", value=session.format_life())

    embed.add_field(name="Time to answer", value=session.time_per_question)

    if session.hardcore_mode:
        embed.add_field(name="Hardcore mode", value="Enabled", inline=True)

    if session.genres is not None:
        embed.add_field(
            name="Genres", value=", ".join([str(g) for g in session.genres])
        )

    embed.add_field(name="Final Scores", value=session.print_score_list(), inline=False)

    if footer is not None:
        embed.set_footer(text=footer)
    else:
        tips = STATIC_TIPS.copy()
        tips.extend(
            [
                f"Use `{session.ctx.clean_prefix}guess leaderboard` to view the server leaderboard.",
                f"{session.ctx.clean_prefix}guess character-age",
                f"Heartbreaking: The Worst Person You Know Is Good At {session.ctx.clean_prefix}guess",
            ]
        )

        if session.question_count is not None:
            tips.extend(
                [
                    f"always go for {session.question_count}/{session.question_count}. nothing else has meaning",
                    f"score goes up to {session.question_count} btw",
                ]
            )

        embed.set_footer(text=random.choice(tips))

    retry_btn = RetryGameButton(
        mode=session.game_type,
        difficulty=session.difficulty,
        questions=session.question_count or 20,
        score=session.score_limit,
        time=session.time_per_question,
        wrong=session.wrong_answers_limit,
        hardcore=session.hardcore_mode,
        genres=session.genres,
    )

    if len(retry_btn.custom_id) <= 100:
        view = discord.ui.View(timeout=None)
        view.add_item(retry_btn)
    else:
        view = MISSING

    await session.channel.send(embed=embed, view=view)


class EndGameTimedOut(GuessingGameState):
    def __init__(self, session: GuessingGameSession, n_unanswered: int) -> None:
        self.session = session
        self.n_unanswered = n_unanswered

    @override
    async def __call__(self) -> "GuessingGameState | None":
        await end_game(
            self.session,
            discord.Color.red(),
            f"{self.n_unanswered} question{'' if self.n_unanswered == 1 else 's'} in a row went unanswered.",
            show_lives=False,
        )
        return None


class EndGameReachedQuestionLimit(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        await end_game(
            self.session,
            discord.Color.green(),
            "The question limit has been reached.",
        )
        return None


class EndGameReachedScoreLimit(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        await end_game(
            self.session,
            discord.Color.green(),
            "The score limit has been reached.",
        )
        return None


class EndGameUserCanceled(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        if session.stopped_by is None:
            msg = "Cannot reach this state if stopped_by is None."
            raise ValueError(msg)

        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        if self.session.stopped_by == self.session.bot.user:
            await end_game(
                self.session,
                discord.Color.yellow(),
                "I'm going down for an update. See you in about five minutes!",
                footer="This beer guy keeps messing with my code...",
                show_lives=False,
            )
        elif self.session.stopped_by is not None:  # this should always be true
            await end_game(
                self.session,
                discord.Color.red(),
                f"The game was stopped by {self.session.stopped_by.mention}.",
                show_lives=False,
            )

        return None


class EndGameTooManyWrongAnswers(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        if session.wrong_answers_limit is None:
            msg = "Cannot reach this state if wrong answers limit is not set."
            raise ValueError(msg)

        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        await end_game(
            self.session,
            discord.Color.red(),
            f"More than {self.session.wrong_answers_limit} question{'s' if self.session.wrong_answers_limit != 1 else ''} was answered wrongly.",
        )
        return None
