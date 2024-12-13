from configparser import ConfigParser
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from configparser import SectionProxy


class BotConfig:
    def __init__(self, section: "SectionProxy") -> None:
        self.__section = section

    @property
    def token(self) -> str:
        return self.__section.get("token")

    @property
    def default_prefix(self) -> str:
        return self.__section.get("default_prefix", fallback="c>")

    @property
    def db_connection_string(self) -> str:
        return self.__section.get(
            "db_connection_string",
            fallback="sqlite+aiosqlite:///data/database.sqlite3",
        )

    @property
    def db_encryption_key(self) -> str | None:
        return self.__section.get("db_encryption_key")

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
        return self.__section.get("listen_address", fallback="127.0.0.1")

    @property
    def port(self) -> Optional[int]:
        return self.__section.getint("port", fallback=5730)

    @property
    def base_url(self) -> Optional[str]:
        return self.__section.get("base_url")

    @property
    def goatcounter(self) -> Optional[str]:
        return self.__section.get("goatcounter")


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


class IconsConfig:
    __slots__ = (
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
    )

    def __init__(self, section: "SectionProxy") -> None:
        self.__section = section

        for k in self.__slots__:
            if k.startswith("__"):
                continue
            setattr(self, k, self.__section.get(k))


class LegalConfig:
    def __init__(self, section: "SectionProxy") -> None:
        self.__section = section

    @property
    def privacy_policy(self) -> str:
        return self.__section.get(
            "privacy_policy",
            fallback="https://www.freeprivacypolicy.com/live/3614793b-5552-4114-a244-b194a3eb881d",
        )

    @property
    def terms_of_service(self) -> str:
        return self.__section.get(
            "terms_of_service",
            fallback="https://www.freeprivacypolicy.com/live/506521e6-0d1a-452e-9071-dd140fbdd618",
        )


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
