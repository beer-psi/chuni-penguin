from dataclasses import dataclass


@dataclass(slots=True, kw_only=True)
class LoginBonusItem:
    day: int
    icon_url: str
    name: str
    obtained: bool = False


@dataclass(slots=True, kw_only=True)
class MonthlyLoginBonus:
    name: str
    days_logged_in: int
    rewards: list[LoginBonusItem]


@dataclass(slots=True, kw_only=True)
class DailyBonus:
    weekday: int
    icon_url: str
    bonus: str
    is_today: bool = False

    @property
    def weekday_name(self) -> str:
        return [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ][self.weekday]


@dataclass(slots=True, kw_only=True)
class LoginBonus:
    received_bonus_today: bool

    monthly_login_bonus: list[MonthlyLoginBonus]
    login_bonus: list[LoginBonusItem]
    daily_bonus: list[DailyBonus]
