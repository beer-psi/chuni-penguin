from abc import ABC, abstractmethod
from types import TracebackType
from typing import ClassVar

from .types import (
    CourseRecord,
    Difficulty,
    Leaderboard,
    LoginBonus,
    PersonalBest,
    Profile,
    RecentScore,
)


class Network(ABC):
    NAME: ClassVar[str]
    """The network's name."""

    ACCENT_COLOR: ClassVar[int]
    """
    The network's accent color, used as a replacement when other data are not available
    (e.g. displaying the acccent color instead of possession color on networks without
    possession).
    """

    RANDOMIZE_USER_AGENT: ClassVar[bool] = False
    """
    Indicate to the user that the network should have its user agent randomized to circumvent
    anti-scraping measures.
    """

    DEFAULT_RATING_SYSTEM: ClassVar[str] = "Rating"
    """
    The network's default rating system name.
    """

    SUPPORTS_LOGOUT: ClassVar[bool] = False
    """
    This network supports :meth:`logout`.
    """

    SUPPORTS_PROFILE: ClassVar[bool] = False
    """
    This network supports :meth:`get_profile`.
    """

    SUPPORTS_USER_AVATAR_IN_PROFILE: ClassVar[bool] = False
    """
    This network returns the player's penguin avatar when fetching the profile
    using :meth:`get_profile`.
    """

    SUPPORTS_RECENT_SCORES: ClassVar[bool] = False
    """
    This network supports :meth:`get_recent_scores`.
    """

    SUPPORTS_DETAILED_RECENT_SCORE: ClassVar[bool] = False
    """
    This network supports :meth:`get_detailed_recent_score`.
    """

    SUPPORTS_PERSONAL_BESTS: ClassVar[bool] = False
    """
    This network supports :meth:`get_personal_best`.
    """

    SUPPORTS_PERSONAL_BESTS_BY_LEVEL: ClassVar[bool] = False
    """
    This network supports :meth:`get_personal_bests_by_level`.
    """

    SUPPORTS_PERSONAL_BESTS_BY_DIFFICULTY: ClassVar[bool] = False
    """
    This network supports :meth:`get_personal_bests_by_difficulty`.
    """

    SUPPORTS_PERSONAL_BESTS_ON_SONG: ClassVar[bool] = False
    """
    This network supports :meth:`get_personal_bests_on_song`.
    """

    SUPPORTS_BEST_RATINGS: ClassVar[bool] = False
    """
    This network supports :meth:`get_best_ratings`.
    """

    SUPPORTS_BEST30: ClassVar[bool] = False
    """
    This network supports :meth:`get_best30`.
    """

    SUPPORTS_NEW20: ClassVar[bool] = False
    """
    This network supports :meth:`get_new20`.
    """

    SUPPORTS_CHART_LEADERBOARD: ClassVar[bool] = False
    """
    This network supports :meth:`get_chart_leaderboard`.
    """

    SUPPORTS_COURSE_RECORDS: ClassVar[bool] = False
    """
    This network supports :meth:`get_course_records`.
    """

    SUPPORTS_LOGIN_BONUS_PROGRESS: ClassVar[bool] = False
    """
    This network supports :meth:`get_login_bonus_progress`.
    """

    SUPPORTS_UPDATE_USERNAME: ClassVar[bool] = False
    """
    This network supports :meth:`update_username`.
    """

    SUPPORTS_SEND_FRIEND_REQUEST: ClassVar[bool] = False
    """
    This network supports :meth:`send_friend_request`.
    """

    @abstractmethod
    def __init__(self, authentication: str): ...

    @property
    @abstractmethod
    def authentication(self) -> str:
        """
        Returns the current authentication data, since it may have been mutated,
        e.g. due to cookie auth.
        """
        ...

    @property
    def user_agent(self) -> str:
        """
        Returns the user-agent on HTTP-based networks, or an empty string.
        """
        return ""

    @user_agent.setter
    def user_agent(self, value: str) -> None:
        """
        Sets the user-agent on HTTP-based networks.
        """
        return

    async def logout(self) -> None:
        """Invalidates the given authentication on the network."""
        raise NotImplementedError

    async def get_minimal_profile(self) -> Profile:
        """
        Get a minimal profile (only required attributes guaranteed), for when a full
        profile is not needed. By default, this delegates to :meth:`get_profile`.
        """
        return await self.get_profile()

    async def get_profile(self) -> Profile:
        """Fetches the user's profile."""
        raise NotImplementedError

    async def get_recent_scores(self) -> list[RecentScore]:
        """Get the user's recently played scores."""
        raise NotImplementedError

    async def get_detailed_recent_score(self, score: RecentScore) -> RecentScore:
        """
        Fill in more details about a recent score. Should return a new score
        instead of mutating the old one.
        """
        raise NotImplementedError

    async def get_personal_bests(self) -> list[PersonalBest]:
        """
        Get the user's personal bests on all charts.
        """
        raise NotImplementedError

    async def get_personal_bests_by_level(self, level: str) -> list[PersonalBest]:
        """
        Get the user's personal bests on a specific level.
        """
        raise NotImplementedError

    async def get_personal_bests_by_difficulty(
        self, difficulty: Difficulty
    ) -> list[PersonalBest]:
        """
        Get the user's personal bests on a specific difficulty.
        """
        raise NotImplementedError

    async def get_personal_bests_on_song(self, song_id: int) -> list[PersonalBest]:
        """Get the user's personal bests on a chart's song."""
        raise NotImplementedError

    async def get_best_ratings(self) -> list[PersonalBest]:
        """
        Get the user's best scores, ordered by the score's play rating from highest
        to lowest, regardless of the rating frame.
        """
        raise NotImplementedError

    async def get_best30(self) -> list[PersonalBest]:
        """Get the user's scores in their best 30 rating frame."""
        raise NotImplementedError

    async def get_new20(self) -> list[PersonalBest]:
        """Get the user's scores in their new 20 rating frame."""
        raise NotImplementedError

    async def get_chart_leaderboard(
        self, song_id: int, difficulty: Difficulty
    ) -> Leaderboard:
        """
        Get the network's leaderboard on the specified song ID and difficulty.
        """
        raise NotImplementedError

    async def get_course_records(self) -> list[CourseRecord]:
        """Get the user's personal bests on courses."""
        raise NotImplementedError

    async def get_login_bonus_progress(self) -> LoginBonus:
        """Get the user's login bonus progress."""
        raise NotImplementedError

    async def update_username(self, new_username: str) -> None:
        """Change the player's username on the network."""
        raise NotImplementedError

    async def send_friend_request(self, identifier: str) -> None:
        """Send a friend request to another player on the network."""
        raise NotImplementedError

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
