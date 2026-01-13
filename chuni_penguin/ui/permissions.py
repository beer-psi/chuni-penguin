from collections.abc import Sequence
from typing import override

import discord

from chuni_penguin.context import PenguinContext
from chuni_penguin.database import CommandPermission
from chuni_penguin.database.guilds import (
    PrimaryPermissionTarget,
    SecondaryPermissionTarget,
)

from ._pagination import FormatPageReturn, ListPageSource, PaginationView


class PermissionsPageSource(ListPageSource[CommandPermission]):
    def __init__(self, entries: list[CommandPermission], *, per_page: int) -> None:
        super().__init__(entries, per_page=per_page)

    @override
    async def format_page(
        self, menu: "PaginationView", page: Sequence[CommandPermission]
    ) -> FormatPageReturn:
        permission_list = []

        for permission in page:
            if permission.primary_target_type == PrimaryPermissionTarget.guild:
                primary = "Server"
            elif permission.primary_target_type == PrimaryPermissionTarget.role:
                primary = f"<@&{permission.primary_target_id}>"
            elif permission.primary_target_type == PrimaryPermissionTarget.channel:
                primary = f"<#{permission.primary_target_id}>"
            elif permission.primary_target_type == PrimaryPermissionTarget.user:
                primary = f"<@{permission.primary_target_id}>"
            else:
                primary = f"Unknown {permission.primary_target_id}"

            if permission.secondary_target_type == SecondaryPermissionTarget.all:
                secondary = "All commands"
            elif permission.secondary_target_type == SecondaryPermissionTarget.command:
                secondary = f"Command `{permission.secondary_target_name}`"
            elif permission.secondary_target_type == SecondaryPermissionTarget.group:
                secondary = f"Group `{permission.secondary_target_name}`"
            else:
                secondary = f"Unknown `{permission.secondary_target_name}`"

            enabled = (
                "\N{WHITE HEAVY CHECK MARK} Enabled"
                if permission.is_allowed
                else "\N{CROSS MARK} Disabled"
            )

            permission_list.append(
                f"{permission.index + 1}. {primary} - {secondary} - {enabled}"
            )

        return {
            "embed": discord.Embed(
                color=discord.Color.yellow(),
                title="Permissions",
                description="\n".join(permission_list),
            )
        }


class PermissionListView(PaginationView):
    def __init__(self, ctx: PenguinContext, permissions: list[CommandPermission]):
        super().__init__(ctx, PermissionsPageSource(permissions, per_page=15))
