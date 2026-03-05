from typing import TYPE_CHECKING, Annotated

import discord
from discord.ext import commands
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert

from chuni_penguin.context import PenguinContext, PenguinGuildContext
from chuni_penguin.converters import CommandOrGroupConverter
from chuni_penguin.database import CommandPermission
from chuni_penguin.database.guilds import (
    PrimaryPermissionTarget,
    SecondaryPermissionTarget,
)
from chuni_penguin.errors import CommandDisabled
from chuni_penguin.ui.permissions import PermissionListView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class PermissionsCog(commands.Cog, name="Permissions"):
    def __init__(self, bot: "ChuniBot"):
        self.bot = bot
        self.permission_cache: dict[int, list[CommandPermission]] = {}

    async def _load_permissions(self, guild_id: int | None = None):
        if guild_id is not None:
            self.permission_cache[guild_id] = []
        else:
            self.permission_cache = {}

        async with self.bot.begin_db_session() as session:
            query = select(CommandPermission).order_by(
                CommandPermission.guild_id, CommandPermission.index
            )

            if guild_id is not None:
                query = query.where(CommandPermission.guild_id == guild_id)

            perms = (await session.execute(query)).scalars().all()

        for perm in perms:
            self.permission_cache.setdefault(perm.guild_id, []).append(perm)

    async def _add_permission(
        self,
        guild_id: int,
        primary_target_type: PrimaryPermissionTarget,
        primary_target_id: int,
        secondary_target: commands.Command | commands.Cog | None,
        *,
        is_allowed: bool,
    ):
        if secondary_target is None:
            secondary_target_type = SecondaryPermissionTarget.all
            secondary_target_name = ""
        elif isinstance(secondary_target, commands.Command):
            secondary_target_type = SecondaryPermissionTarget.command
            secondary_target_name = secondary_target.qualified_name
        else:
            secondary_target_type = SecondaryPermissionTarget.group
            secondary_target_name = secondary_target.qualified_name

        async with self.bot.begin_db_session() as session:
            query = select(func.max(CommandPermission.index)).where(
                CommandPermission.guild_id == guild_id
            )
            max_index = (await session.execute(query)).scalar_one_or_none()

            query = insert(CommandPermission).values(
                guild_id=guild_id,
                index=0 if max_index is None else max_index + 1,
                primary_target_type=primary_target_type,
                primary_target_id=primary_target_id,
                secondary_target_type=secondary_target_type,
                secondary_target_name=secondary_target_name,
                is_allowed=is_allowed,
            )
            query = query.on_conflict_do_update(
                index_elements=[
                    CommandPermission.primary_target_type,
                    CommandPermission.primary_target_id,
                    CommandPermission.secondary_target_type,
                    CommandPermission.secondary_target_name,
                ],
                set_={"is_allowed": query.excluded.is_allowed},
            )
            await session.execute(query)
            await session.commit()

        await self._load_permissions(guild_id)

    async def cog_load(self) -> None:
        await self._load_permissions()

    def get_permission(
        self,
        group_name: str | None,
        command_name: str,
        guild_id: int,
        channel_id: int | None,
        author_id: int,
        role_ids: set[int],
    ) -> CommandPermission | None:
        permissions = self.permission_cache.get(guild_id, [])

        for permission in permissions:
            # If permission is for a command, but there's no command, or the permission
            # doesn't target the executed command
            if (
                permission.secondary_target_type == SecondaryPermissionTarget.command
                and permission.secondary_target_name != "*"
                and command_name != permission.secondary_target_name
            ):
                continue

            if (
                permission.secondary_target_type == SecondaryPermissionTarget.group
                and permission.secondary_target_name != "*"
                and group_name != permission.secondary_target_name
            ):
                continue

            if (
                permission.primary_target_type == PrimaryPermissionTarget.user
                and author_id == permission.primary_target_id
            ):
                return permission

            if (
                permission.primary_target_type == PrimaryPermissionTarget.channel
                and channel_id == permission.primary_target_id
            ):
                return permission

            if (
                permission.primary_target_type == PrimaryPermissionTarget.role
                and permission.primary_target_id in role_ids
            ):
                return permission

            # Permission applies to the entire server
            if permission.primary_target_type == PrimaryPermissionTarget.guild:
                return permission

        return None

    async def permissions_check(self, ctx: PenguinContext):
        if ctx.command is None:
            return True

        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return True

        # Prevent permission lockouts
        if ctx.author.guild_permissions.manage_guild:
            return True

        if isinstance(ctx.command, discord.app_commands.Command):
            cog_name = (
                ctx.command.binding.qualified_name
                if ctx.command.binding is not None
                else None
            )
        else:
            cog_name = ctx.command.cog_name

        permission = self.get_permission(
            cog_name,
            ctx.command.qualified_name,
            ctx.guild.id,
            ctx.channel.id,
            ctx.author.id,
            {role.id for role in ctx.author.roles},
        )

        if permission is None:
            return True

        if permission.is_allowed:
            return True

        raise CommandDisabled(permission)

    async def permissions_interaction_check(self, interaction: discord.Interaction):
        if interaction.command is None:
            return True

        if interaction.guild_id is None or not isinstance(
            interaction.user, discord.Member
        ):
            return True

        # Prevent permission lockouts
        if interaction.user.guild_permissions.manage_guild:
            return True

        if (
            isinstance(interaction.command, discord.app_commands.ContextMenu)
            and interaction.command.qualified_name == "View your score"
        ):
            # Manual group binding since context menu don't really have groups
            group_name = "Records"
        elif (
            isinstance(interaction.command, discord.app_commands.Command)
            and interaction.command.binding is not None
        ):
            group_name = interaction.command.binding.qualified_name
        else:
            group_name = None

        permission = self.get_permission(
            group_name,
            interaction.command.qualified_name,
            interaction.guild_id,
            interaction.channel_id,
            interaction.user.id,
            {role.id for role in interaction.user.roles},
        )

        if permission is None:
            return True

        if permission.is_allowed:
            return True

        await interaction.response.send_message(
            embed=discord.Embed(
                color=discord.Color.red(),
                title="Error",
                description=str(CommandDisabled(permission)),
            ),
            ephemeral=True,
        )
        return False

    @commands.hybrid_group("permissions", aliases=["perms", "permission", "perm"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions(self, ctx: PenguinContext):
        """Enable or disable text commands for the server, or a role, channel or member.

        This will also work with *most* slash commands, however for more precise control you should check out [dedicated slash command permissions](https://support-apps.discord.com/hc/en-us/articles/26501869403159-Command-Permissions), which also has the benefit that disallowed commands will not show up in users' command list.

        The permission system works by going down the permission list (see `$PREFIXpermissions list`) and returning on the first rule that matches the current invocation (based on server, role, channel or member). Therefore, it is important that your permissions are ordered correctly (see `$PREFIXpermissions move`).

        Members with the Manage Server permission can edit command permissions and are always able to run commands.
        """

        await self.permissions_list.invoke(ctx)

    @permissions.command("list", aliases=["ls"])  # pyright: ignore[reportFunctionMemberAccess]
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_list(self, ctx: PenguinGuildContext):
        """List the command permissions for this server."""

        perms = self.permission_cache.get(ctx.guild.id, [])

        if len(perms) <= 0:
            await ctx.respond_or_edit("This server has no command permissions set up.")
            return

        view = PermissionListView(ctx, perms)
        await view.start()

    @permissions.command("move", aliases=["mv"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_move(
        self, ctx: PenguinGuildContext, source: int, destination: int
    ):
        """Move a permission from one position to another in the list."""

        if source == destination:
            msg = "Cannot move a permission to the same position."
            raise commands.BadArgument(msg)

        if source < 1 or destination < 1:
            msg = "Source or destination cannot be smaller than 1."
            raise commands.BadArgument(msg)

        source_idx = source - 1
        destination_idx = destination - 1

        async with self.bot.begin_db_session() as session, ctx.typing():
            query = select(CommandPermission).where(
                (CommandPermission.guild_id == ctx.guild.id)
                & (CommandPermission.index == source_idx)
            )
            perm = (await session.execute(query)).scalar_one_or_none()

            if perm is None:
                msg = f"There are no permissions at position {source}."
                raise commands.BadArgument(msg)

            query = select(func.max(CommandPermission.index)).where(
                CommandPermission.guild_id == ctx.guild.id
            )
            max_index = (await session.execute(query)).scalar_one()

            if destination_idx > max_index:
                msg = f"Cannot move permission to position {destination}, there are only {max_index + 1} permissions."
                raise commands.BadArgument(msg)

            # Remove permission at source_idx, so everything behind it is shifted up
            # 1 index
            query = (
                update(CommandPermission)
                .values(index=CommandPermission.index - 1)
                .where(
                    (CommandPermission.guild_id == ctx.guild.id)
                    & (CommandPermission.index > source_idx)
                    & (CommandPermission.id != perm.id)
                )
            )
            await session.execute(query)

            # Add it back at destination_idx, so everything behind it is shifted down
            # 1 index
            query = (
                update(CommandPermission)
                .values(index=CommandPermission.index + 1)
                .where(
                    (CommandPermission.guild_id == ctx.guild.id)
                    & (CommandPermission.index >= destination_idx)
                    & (CommandPermission.id != perm.id)
                )
            )
            await session.execute(query)

            # Move source position to new place
            query = (
                update(CommandPermission)
                .values(index=destination_idx)
                .where(CommandPermission.id == perm.id)
            )
            await session.execute(query)

            await session.commit()

        await self._load_permissions(ctx.guild.id)

        await ctx.respond_or_edit(
            f"Moved permission at position {source} to position {destination}."
        )

    @permissions.command("delete", aliases=["remove", "rm", "del"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_delete(self, ctx: PenguinGuildContext, position: int):
        """Deletes the permission at the given position."""

        if position < 1:
            msg = "Position cannot be smaller than 1."
            raise commands.BadArgument(msg)

        position_idx = position - 1

        async with self.bot.begin_db_session() as session, ctx.typing():
            query = delete(CommandPermission).where(
                (CommandPermission.guild_id == ctx.guild.id)
                & (CommandPermission.index == position_idx)
            )
            await session.execute(query)

            # This should be a no-op if the perm at position_idx doesn't exist, since
            # index is contiguous and non-negaative.
            query = (
                update(CommandPermission)
                .values(index=CommandPermission.index - 1)
                .where(
                    (CommandPermission.guild_id == ctx.guild.id)
                    & (CommandPermission.index > position_idx)
                )
            )
            await session.execute(query)
            await session.commit()

        await self._load_permissions(ctx.guild.id)
        await ctx.respond_or_edit(f"Deleted permission at position {position}.")

    @permissions.command("reset")
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_reset(self, ctx: PenguinGuildContext):
        """Resets all permissions for this server."""

        async with self.bot.begin_db_session() as session, ctx.typing():
            query = delete(CommandPermission).where(
                CommandPermission.guild_id == ctx.guild.id
            )

            await session.execute(query)
            await session.commit()

        self.permission_cache[ctx.guild.id] = []

        await ctx.respond_or_edit("Permissions for this server have been reset.")

    @permissions.command("server", aliases=["guild", "s", "g"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_server(
        self,
        ctx: PenguinGuildContext,
        command_or_group: Annotated[
            commands.Command | commands.Cog, CommandOrGroupConverter
        ],
        *,
        is_allowed: bool,
    ):
        """Enable or disable a command or group at the server level."""

        async with ctx.typing():
            await self._add_permission(
                ctx.guild.id,
                PrimaryPermissionTarget.guild,
                ctx.guild.id,
                command_or_group,
                is_allowed=is_allowed,
            )

        enable_disable = "Enabled" if is_allowed else "Disabled"
        command_group = (
            "command" if isinstance(command_or_group, commands.Command) else "group"
        )

        await ctx.respond_or_edit(
            f"{enable_disable} the {command_group} `{command_or_group.qualified_name}` for this server."
        )

    @permissions.command("serverall", aliases=["guildall", "sa", "ga"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_server_all(
        self, ctx: PenguinGuildContext, *, is_allowed: bool
    ):
        """Enable or disable all commands at the server level."""

        async with ctx.typing():
            await self._add_permission(
                ctx.guild.id,
                PrimaryPermissionTarget.guild,
                ctx.guild.id,
                None,
                is_allowed=is_allowed,
            )

        enable_disable = "Enabled" if is_allowed else "Disabled"

        await ctx.respond_or_edit(f"{enable_disable} all commands for this server.")

    @permissions.command("role", aliases=["r"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_role(
        self,
        ctx: PenguinGuildContext,
        command_or_group: Annotated[
            commands.Command | commands.Cog, CommandOrGroupConverter
        ],
        role: discord.Role,
        *,
        is_allowed: bool,
    ):
        """Enable or disable a command or group at the role level."""

        async with ctx.typing():
            await self._add_permission(
                ctx.guild.id,
                PrimaryPermissionTarget.role,
                role.id,
                command_or_group,
                is_allowed=is_allowed,
            )

        enable_disable = "Enabled" if is_allowed else "Disabled"
        command_group = (
            "command" if isinstance(command_or_group, commands.Command) else "group"
        )

        await ctx.respond_or_edit(
            f"{enable_disable} the {command_group} `{command_or_group.qualified_name}` for the role {role.mention}."
        )

    @permissions.command("roleall", aliases=["ra"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_role_all(
        self, ctx: PenguinGuildContext, role: discord.Role, *, is_allowed: bool
    ):
        """Enable or disable all commands at the role level."""

        async with ctx.typing():
            await self._add_permission(
                ctx.guild.id,
                PrimaryPermissionTarget.role,
                role.id,
                None,
                is_allowed=is_allowed,
            )

        enable_disable = "Enabled" if is_allowed else "Disabled"

        await ctx.respond_or_edit(
            f"{enable_disable} all commands for the role {role.mention}."
        )

    @permissions.command("channel", aliases=["ch", "c"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_channel(
        self,
        ctx: PenguinGuildContext,
        command_or_group: Annotated[
            commands.Command | commands.Cog, CommandOrGroupConverter
        ],
        channel: discord.abc.GuildChannel,
        *,
        is_allowed: bool,
    ):
        """Enable or disable a command or group at the channel level."""

        async with ctx.typing():
            await self._add_permission(
                ctx.guild.id,
                PrimaryPermissionTarget.channel,
                channel.id,
                command_or_group,
                is_allowed=is_allowed,
            )

        enable_disable = "Enabled" if is_allowed else "Disabled"
        command_group = (
            "command" if isinstance(command_or_group, commands.Command) else "group"
        )

        await ctx.respond_or_edit(
            f"{enable_disable} the {command_group} `{command_or_group.qualified_name}` for the channel {channel.mention}."
        )

    @permissions.command("channelall", aliases=["ca", "cha"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_channel_all(
        self,
        ctx: PenguinGuildContext,
        channel: discord.abc.GuildChannel,
        *,
        is_allowed: bool,
    ):
        """Enable or disable all commands at the channel level."""

        async with ctx.typing():
            await self._add_permission(
                ctx.guild.id,
                PrimaryPermissionTarget.channel,
                channel.id,
                None,
                is_allowed=is_allowed,
            )

        enable_disable = "Enabled" if is_allowed else "Disabled"

        await ctx.respond_or_edit(
            f"{enable_disable} all commands for the channel {channel.mention}."
        )

    @permissions.command("member", aliases=["user", "m", "u"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_member(
        self,
        ctx: PenguinGuildContext,
        command_or_group: Annotated[
            commands.Command | commands.Cog, CommandOrGroupConverter
        ],
        member: discord.Member,
        *,
        is_allowed: bool,
    ):
        """Enable or disable a command or group at the member level."""

        async with ctx.typing():
            await self._add_permission(
                ctx.guild.id,
                PrimaryPermissionTarget.user,
                member.id,
                command_or_group,
                is_allowed=is_allowed,
            )

        enable_disable = "Enabled" if is_allowed else "Disabled"
        command_group = (
            "command" if isinstance(command_or_group, commands.Command) else "group"
        )

        await ctx.respond_or_edit(
            f"{enable_disable} the {command_group} `{command_or_group.qualified_name}` for the member {member.mention}."
        )

    @permissions.command("memberall", aliases=["userall", "ma", "ua"])
    @commands.has_guild_permissions(manage_guild=True)
    async def permissions_member_all(
        self,
        ctx: PenguinGuildContext,
        member: discord.Member,
        *,
        is_allowed: bool,
    ):
        """Enable or disable all commands at the member level."""

        async with ctx.typing():
            await self._add_permission(
                ctx.guild.id,
                PrimaryPermissionTarget.user,
                member.id,
                None,
                is_allowed=is_allowed,
            )

        enable_disable = "Enabled" if is_allowed else "Disabled"

        await ctx.respond_or_edit(
            f"{enable_disable} all commands for the member {member.mention}."
        )


async def setup(bot: "ChuniBot"):
    await bot.add_cog(PermissionsCog(bot))
