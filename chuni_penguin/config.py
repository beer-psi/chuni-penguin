from configparser import ConfigParser
from pathlib import Path
from typing import TYPE_CHECKING, Optional, overload

if TYPE_CHECKING:
    from configparser import SectionProxy

    from chuni_penguin.networks.types import Rank


class BotConfig:
    def __init__(self, section: "SectionProxy") -> None:
        self.__section = section

    @property
    def token(self) -> str:
        return self.__section["token"]

    @property
    def default_prefix(self) -> str:
        return self.__section.get("default_prefix", fallback="c>")  # pyright: ignore[reportReturnType]

    @property
    def db_connection_string(self) -> str:
        return self.__section.get(
            "db_connection_string",
            fallback="sqlite+aiosqlite:///data/database.sqlite3",
        )  # pyright: ignore[reportReturnType]

    @property
    def error_reporting_webhook(self) -> Optional[str]:
        return self.__section.get("error_reporting_webhook")

    @property
    def alias_managers(self) -> list[int]:
        raw = self.__section.get("alias_managers", "").strip()
        if len(raw) == 0:
            return []

        return [int(x) for x in raw.split(",")]

    @property
    def support_server_invite(self) -> str | None:
        return self.__section.get("support_server_invite")


class WebConfig:
    def __init__(self, section: "SectionProxy") -> None:
        self.__section = section

    @property
    def enable(self) -> bool:
        return self.__section.getboolean("enable", fallback=False)

    @property
    def listen_address(self) -> str:
        return self.__section.get("listen_address", fallback="127.0.0.1")  # pyright: ignore[reportReturnType]

    @property
    def port(self) -> Optional[int]:
        return self.__section.getint("port", fallback=5730)

    @property
    def base_url(self) -> Optional[str]:
        return self.__section.get("base_url")

    @property
    def goatcounter(self) -> Optional[str]:
        return self.__section.get("goatcounter")

    @property
    def serve_assets(self) -> bool:
        return self.__section.getboolean("serve_assets", fallback=False)

    @property
    def is_accessible(self):
        return (
            self.enable
            and self.base_url is not None
            and "127.0.0.1" not in self.base_url
            and "localhost" not in self.base_url
        )

    @property
    def fallback_url(self) -> str | None:
        return self.__section.get("fallback_url")

    @property
    def trust_proxy(self) -> bool:
        return self.__section.getboolean("trust_proxy", fallback=False)


class CredentialsConfig:
    def __init__(self, section: "SectionProxy") -> None:
        self.__section = section

    @property
    def chunirec_token(self) -> Optional[str]:
        return self.__section.get("chunirec_token")

    @property
    def kamaitachi_client_id(self) -> Optional[str]:
        return self.__section.get("kamaitachi_client_id")

    @property
    def kamaitachi_client_secret(self) -> Optional[str]:
        return self.__section.get("kamaitachi_client_secret")

    @property
    def kamaitachi_api_key(self) -> Optional[str]:
        return self.__section.get("kamaitachi_api_key")

    @property
    def goatcounter_api_key(self) -> Optional[str]:
        return self.__section.get("goatcounter_api_key")

    @property
    def sega_id_username(self) -> Optional[str]:
        return self.__section.get("sega_id_username")

    @property
    def sega_id_password(self) -> Optional[str]:
        return self.__section.get("sega_id_password")


class IconsConfig:
    __slots__ = (  # noqa: RUF023
        "__section",
        "sssp",
        "sss",
        "ssp",
        "ss",
        "sp",
        "s",
        "aaa",
        "aa",
        "a",
        "bbb",
        "bb",
        "b",
        "c",
        "d",
        "bonus_icon_map",
        "bonus_icon_exp",
        "bonus_icon_point",
        "bonus_icon_chance",
        "bonus_icon_critical",
        "bonus_icon_gamepoint",
        "bonus_icon_selection",
    )

    def __init__(self, section: "SectionProxy") -> None:
        self.__section = section

        for k in self.__slots__:
            if k.startswith("__"):
                continue
            setattr(self, k, self.__section.get(k))

    @overload
    def icon(self, named: str) -> str | None: ...

    @overload
    def icon(self, named: str, fallback: str) -> str: ...

    def icon(self, named: str, fallback: str | None = None) -> str | None:
        try:
            return getattr(self, named) or fallback
        except AttributeError:
            return fallback

    def rank_icon(self, rank: "str | Rank") -> str:
        return self.icon(str(rank).lower().replace("+", "p"), str(rank))


class LegalConfig:
    def __init__(self, section: "SectionProxy") -> None:
        self.__section = section

    @property
    def privacy_policy(self) -> str:
        return self.__section.get(
            "privacy_policy",
            fallback="https://chuni-penguin.beerpsi.cc/legal/privacy-policy",
        )  # pyright: ignore[reportReturnType]

    @property
    def terms_of_service(self) -> str:
        return self.__section.get(
            "terms_of_service",
            fallback="https://chuni-penguin.beerpsi.cc/legal/terms-of-service",
        )  # pyright: ignore[reportReturnType]


class DangerousConfig:
    def __init__(self, section: "SectionProxy") -> None:
        self.__section = section

    @property
    def dev(self) -> bool:
        return self.__section.getboolean("dev", fallback=False)


class Config:
    def __init__(self, config: "ConfigParser") -> None:
        self.__config = config
        self.bot = BotConfig(self.__config["bot"])
        self.web = WebConfig(self.__config["web"])
        self.credentials = CredentialsConfig(self.__config["credentials"])
        self.icons = IconsConfig(self.__config["icons"])
        self.legal = LegalConfig(self.__config["legal"])
        self.dangerous = DangerousConfig(self.__config["dangerous"])

    @classmethod
    def from_file(cls, path: "str | Path") -> "Config":
        cfg = ConfigParser()
        cfg.read(path)
        return cls(cfg)


config = Config.from_file(Path(__file__).parent.parent / "bot.ini")
