from configparser import ConfigParser
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar, overload

import msgspec

if TYPE_CHECKING:
    from chuni_penguin.types import Rank

T = TypeVar("T")


class CommaDelimitedSet(set[T], Generic[T]):
    pass


class BotConfig(msgspec.Struct):
    token: str
    default_prefix: str = "c>"
    db_connection_string: str = "sqlite+aiosqlite:///data/database.sqlite3"
    error_reporting_webhook: str | None = None
    alias_managers: CommaDelimitedSet[int] = msgspec.field(
        default_factory=CommaDelimitedSet
    )
    support_server_invite: str | None = None


class WebConfig(msgspec.Struct):
    enable: bool = False
    listen_address: str = "127.0.0.1"
    port: int = 5730
    base_url: str | None = None
    goatcounter: str | None = None
    serve_assets: bool = False
    fallback_url: str | None = None
    trust_proxy: bool = False
    is_accessible: bool = False

    def __post_init__(self):
        self.is_accessible = (
            self.enable
            and self.base_url is not None
            and "127.0.0.1" not in self.base_url
            and "localhost" not in self.base_url
        )


class CredentialsConfig(msgspec.Struct):
    chunirec_token: str | None = None
    kamaitachi_client_id: str | None = None
    kamaitachi_client_secret: str | None = None
    kamaitachi_api_key: str | None = None
    goatcounter_api_key: str | None = None
    sega_id_username: str | None = None
    sega_id_password: str | None = None
    kofi_verification_token: str | None = None
    git_auth_username: str | None = None
    git_auth_password: str | None = None


class IconsConfig(msgspec.Struct):
    sssp: str | None = None
    sss: str | None = None
    ssp: str | None = None
    ss: str | None = None
    sp: str | None = None
    s: str | None = None
    aaa: str | None = None
    aa: str | None = None
    a: str | None = None
    bbb: str | None = None
    bb: str | None = None
    b: str | None = None
    c: str | None = None
    d: str | None = None
    bonus_icon_map: str | None = None
    bonus_icon_exp: str | None = None
    bonus_icon_point: str | None = None
    bonus_icon_chance: str | None = None
    bonus_icon_critical: str | None = None
    bonus_icon_gamepoint: str | None = None
    bonus_icon_selection: str | None = None
    linked_gate_not_found: str | None = None
    linked_gate_under_analysis: str | None = None
    linked_gate_origin_linkable: str | None = None
    linked_gate_air_linkable: str | None = None
    linked_gate_star_linkable: str | None = None
    linked_gate_amazon_linkable: str | None = None
    linked_gate_crystal_linkable: str | None = None
    linked_gate_paradise_linkable: str | None = None
    linked_gate_new_linkable: str | None = None
    linked_gate_sun_linkable: str | None = None
    linked_gate_luminous_linkable: str | None = None
    linked_gate_verse_linkable: str | None = None
    linked_gate_origin_clear: str | None = None
    linked_gate_air_clear: str | None = None
    linked_gate_star_clear: str | None = None
    linked_gate_amazon_clear: str | None = None
    linked_gate_crystal_clear: str | None = None
    linked_gate_paradise_clear: str | None = None
    linked_gate_new_clear: str | None = None
    linked_gate_sun_clear: str | None = None
    linked_gate_luminous_clear: str | None = None
    linked_gate_verse_clear: str | None = None
    link_level_v: str | None = None
    link_level_iv: str | None = None
    link_level_iii: str | None = None
    link_level_ii: str | None = None
    link_level_i: str | None = None

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


class LegalConfig(msgspec.Struct):
    privacy_policy: str | None = None
    terms_of_service: str | None = None


class DangerousConfig(msgspec.Struct):
    dev: bool = False
    debug_totp: str | None = None


class LocalSeedsConfig(msgspec.Struct, tag="local"):
    path: Path


class GitSeedsConfig(msgspec.Struct, tag="git"):
    url: str
    username: str
    email: str
    branch: str | msgspec.UnsetType = msgspec.UNSET


def config_dec_hook(ty: type, obj: Any):
    # Handle generic types - these have __args__ for parameters and __origin__ for the
    # original type
    try:
        ty_arg = ty.__args__[0] if len(ty.__args__) > 0 else None
        ty = ty.__origin__
    except AttributeError:
        ty_arg = None

    if ty is CommaDelimitedSet and ty_arg is int and isinstance(obj, str):
        return CommaDelimitedSet(int(item.strip()) for item in obj.split(","))

    if issubclass(ty, Path) and isinstance(obj, str):
        return ty(obj)

    msg = f"Objects of type {obj.__class__.__name__} cannot be converted into type {ty}"
    raise NotImplementedError(msg)


class Config:
    __slots__ = (
        "_path",
        "bot",
        "credentials",
        "dangerous",
        "icons",
        "legal",
        "seeds",
        "web",
    )

    def __init__(self, path: "str | Path") -> None:
        self._path = path
        self.reload()

    def reload(self):
        cfg = ConfigParser()

        cfg.read(self._path)

        self.bot = msgspec.convert(
            cfg["bot"], type=BotConfig, strict=False, dec_hook=config_dec_hook
        )
        self.web = msgspec.convert(
            cfg["web"], type=WebConfig, strict=False, dec_hook=config_dec_hook
        )
        self.credentials = msgspec.convert(
            cfg["credentials"],
            type=CredentialsConfig,
            strict=False,
            dec_hook=config_dec_hook,
        )
        self.icons = msgspec.convert(
            cfg["icons"], type=IconsConfig, strict=False, dec_hook=config_dec_hook
        )
        self.legal = msgspec.convert(
            cfg["legal"], type=LegalConfig, strict=False, dec_hook=config_dec_hook
        )
        self.dangerous = msgspec.convert(
            cfg["dangerous"],
            type=DangerousConfig,
            strict=False,
            dec_hook=config_dec_hook,
        )

        if cfg.has_section("seeds"):
            self.seeds = msgspec.convert(
                cfg["seeds"],
                type=LocalSeedsConfig | GitSeedsConfig,
                strict=False,
                dec_hook=config_dec_hook,
            )
        else:
            self.seeds = LocalSeedsConfig(Path("chuni_penguin/database/seeds"))


config = Config(Path(__file__).parent.parent / "bot.ini")
