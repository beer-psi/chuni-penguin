from abc import ABC, abstractmethod
from collections.abc import Sequence
from types import TracebackType
from typing import TYPE_CHECKING, ClassVar

from chuni_penguin.constants import ChunithmVersion
from chuni_penguin.types import (
    CourseRecord,
    Difficulty,
    Genre,
    Leaderboard,
    LinkedGate,
    LinkedGateLeaderboard,
    LinkedGateStatus,
    LoginBonus,
    PersonalBest,
    Profile,
    Rank,
    RatingBreakdown,
    RatingType,
    RecentScore,
)

if TYPE_CHECKING:
    from chuni_penguin.cogs.database import DatabaseCog


class NetworkAdapter(ABC):
    __slots__ = ("database", "discord_id")

    NAME: ClassVar[str]
    """The network's name."""

    ACCENT_COLOR: ClassVar[int]
    """
    The network's accent color, used as a replacement when other data are not available
    (e.g. displaying the acccent color instead of possession color on networks without
    possession).
    """

    DEFAULT_RATING_SYSTEM: ClassVar[RatingType] = RatingType.in_game
    """
    The network's default rating system.
    """

    SUPPORTS_DETAILED_RECENT_SCORE: ClassVar[bool] = False
    """
    This network supports :meth:`get_detailed_recent_score`.
    """

    def __init__(self, database: "DatabaseCog", discord_id: int, *args, **kwargs):
        self.database = database
        self.discord_id = discord_id

    async def get_minimal_profile(self) -> Profile:
        """
        Get a minimal profile (only required attributes guaranteed), for when a full
        profile is not needed. By default, this delegates to :meth:`get_profile`.
        """
        return await self.get_profile()

    @abstractmethod
    async def get_profile(self) -> Profile:
        """Fetches the user's profile."""

    @abstractmethod
    async def get_recent_scores(self) -> list[RecentScore]:
        """Get the user's recently played scores."""

    @abstractmethod
    async def get_detailed_recent_score(self, score: RecentScore) -> RecentScore:
        """
        Fill in more details about a recent score. Returns a new score
        instead of mutating the old one.
        """

    @abstractmethod
    async def get_personal_bests(
        self,
        level: str | None = None,
        difficulty: Difficulty | None = None,
        genre: Genre | None = None,
        rank: Rank | None = None,
        version: ChunithmVersion | None = None,
    ) -> list[PersonalBest]:
        """
        Get the user's personal bests on the list of charts filtered by provided
        parameters.

        Raises `ValueError` if the request cannot be reasonably satisfied (e.g. too
        many network calls needed.)
        """

    @abstractmethod
    async def get_all_personal_bests(self) -> list[PersonalBest]:
        """
        Get all of the user's personal bests, regardless of how many network calls needed.
        """

    @abstractmethod
    async def get_personal_bests_on_song(self, song_id: int) -> list[PersonalBest]:
        """Get the user's personal bests on all charts of a song."""

    @abstractmethod
    async def get_rating_breakdown(self, rating_type: RatingType) -> RatingBreakdown:
        """
        Get the user's rating breakdown for the specified rating system.

        May raise `NotImplementedError` if the network does not support this rating
        system.
        """

    @abstractmethod
    async def get_chart_leaderboard(
        self, song_id: int, difficulty: Difficulty
    ) -> Leaderboard:
        """
        Get the network's leaderboard on the specified song ID and difficulty.
        """

    @abstractmethod
    async def get_course_records(self) -> list[CourseRecord]:
        """Get the user's personal bests on courses."""

    @abstractmethod
    async def get_login_bonus_progress(self) -> LoginBonus:
        """Get the user's login bonus progress."""

    @abstractmethod
    async def update_username(self, new_username: str) -> None:
        """Change the player's username on the network."""

    @abstractmethod
    async def send_friend_request(self, identifier: str) -> None:
        """Send a friend request to another player on the network."""

    @abstractmethod
    async def get_linked_verse_progress(self) -> dict[LinkedGate, LinkedGateStatus]:
        """Get the player's Linked VERSE progress."""

    @abstractmethod
    async def get_linked_gate_leaderboard(
        self, linked_gate: LinkedGate
    ) -> LinkedGateLeaderboard:
        """Get the network's leaderboard for a specific Linked GATE."""

    @abstractmethod
    async def get_favorite_music(self) -> list[int]:
        """Get the player's favorite songs."""

    @abstractmethod
    async def set_favorite_music(self, ids: Sequence[int]) -> None:
        """
        Set the player's favorite music. Any songs that were previously in the list
        but not included in :param:`ids` must be removed.
        """

    @abstractmethod
    async def logout(self) -> None:
        """
        Logs out on the network. The provided credentials (if any)
        should be invalidated.
        """

    async def aclose(self) -> None:
        """
        Clean up any resources associated with this network, e.g. HTTP clients.
        """
        return

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()
