from discord.ext.commands import CheckFailure

from chuni_penguin.database import CommandPermission
from chuni_penguin.database.guilds import (
    PrimaryPermissionTarget,
    SecondaryPermissionTarget,
)


class ChuniBotError(Exception):
    """Base class for all bot exceptions."""


class MissingDetailedParams(ChuniBotError):
    """Raised when a record is missing params for accessing details."""

    def __init__(self) -> None:
        super().__init__("Cannot fetch song details if song.detailed is None.")


class MissingConfiguration(ChuniBotError):
    """Raised when a configuration key is missing."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Configuration file is missing key {key!r}.")


class CommandDisabled(CheckFailure):
    def __init__(self, permission: CommandPermission):
        self.permission = permission

        secondary = (
            f"The {permission.secondary_target_type.name} `{permission.secondary_target_name}` has"
            if permission.secondary_target_type != SecondaryPermissionTarget.all
            else "All commands have"
        )

        if permission.primary_target_type == PrimaryPermissionTarget.guild:
            primary = "this server"
        elif permission.primary_target_type == PrimaryPermissionTarget.role:
            primary = f"the role <@&{permission.primary_target_id}>"
        elif permission.primary_target_type == PrimaryPermissionTarget.channel:
            primary = "this channel"
        elif permission.primary_target_type == PrimaryPermissionTarget.user:
            primary = "you"
        else:
            primary = "???"

        super().__init__(f"{secondary} been disabled for {primary}.")
