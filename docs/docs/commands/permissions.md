Permissions are a way to enable or disable text commands for the server, or specific
sections of it (based on role, channel or user).

Due to how slash commands are implemented, this system also works with *most* slash
commands. However, you should check out Discord's built-in [command permissions](https://support-apps.discord.com/hc/en-us/articles/26501869403159-Command-Permissions)
for finer grained control. Discord's built in system also has the advantage of hiding
commands that users cannot run from their command list.

The permission system is simple: for each command invocation, go down the list of
permissions, return the result from the first permission matching the invocation. For
example, if you have 3 permissions configured:

1. \#general - All commands - Disabled
2. @user1 - Group [Fluff](./fluff.md) - Disabled
3. Server - Group [Fluff](./fluff.md) - Enabled

When @user1 executes a command from group [Fluff](./fluff.md), they will be disallowed
from doing so, because the check stops at permission 2 and never gets to permission 3.
Therefore, it is important to order your permissions correctly.

Members with the Manage Server permission can edit command permissions and are always
able to run commands, in order to prevent lockouts.

## permissions

<small>(aliases: `permission`, `perms`, `perm`)</small>

The base command. Alias of [`permissions list`](#permissions-list).

=== "Text command"

    `c>permissions`

## permissions list

<small>(aliases: `permissions ls`)</small>

List the command permissions for this server.

=== "Text command"

    `c>permissions list`

=== "Slash command"

    `/permissions list`

## permissions move

<small>(aliases: `permissions mv`)</small>

Move a permission from one position to another in the list.

=== "Text command"

    `c>permissions move <source> <destination>`

=== "Slash command"

    `/permissions move source:<source> destination:<destination>`

<h3>Options</h3>

- `source`: The position of the permission to move.
- `destination`: The new position.

## permissions delete

<small>(aliases: `permissions remove`, `permissions del`, `permissions rm`)</small>

Delete the permission at the given position.

=== "Text command"

    `c>permissions delete <position>`

=== "Slash command"

    `/permissions delete position:<position>`

<h3>Options</h3>

- `position`: The position of the permission to delete.

## permissions reset

Reset all permissions for this server.

=== "Text command"

    `c>permissions reset`

=== "Slash command"

    `/permissions reset`

## permissions server

Enable or disable a command or group at the server level.

=== "Text command"

    `c>permissions server <command_or_group> <is_allowed>`

=== "Slash command"

    `/permissions server command_or_group:<command_or_group> is_allowed:<True|False>`

<h3>Options</h3>

- `command_or_group`: The command or group name.
- `is_allowed`: Whether the command is enabled or not.

## permissions serverall

Enable or disable all commands at the server level.

=== "Text command"

    `c>permissions serverall <is_allowed>`

=== "Slash command"

    `/permissions serverall is_allowed:<True|False>`

<h3>Options</h3>

- `is_allowed`: Whether the command is enabled or not.

## permissions role

Enable or disable a command or group at the role level.

=== "Text command"

    `c>permissions role <command_or_group> <role> <is_allowed>`

=== "Slash command"

    `/permissions role command_or_group:<command_or_group> role:<role> is_allowed:<True|False>`

<h3>Options</h3>

- `command_or_group`: The command or group name.
- `role`: The role to apply this permission to.
- `is_allowed`: Whether the command is enabled or not.

## permissions roleall

Enable or disable all commands at the role level.

=== "Text command"

    `c>permissions roleall <role> <is_allowed>`

=== "Slash command"

    `/permissions roleall role:<role> is_allowed:<True|False>`

<h3>Options</h3>

- `role`: The role to apply this permission to.
- `is_allowed`: Whether the command is enabled or not.

## permissions channel

Enable or disable a command or group at the channel level.

=== "Text command"

    `c>permissions channel <command_or_group> <channel> <is_allowed>`

=== "Slash command"

    `/permissions channel command_or_group:<command_or_group> channel:<channel> is_allowed:<True|False>`

<h3>Options</h3>

- `command_or_group`: The command or group name.
- `channel`: The channel to apply this permission to.
- `is_allowed`: Whether the command is enabled or not.

## permissions channelall

Enable or disable all commands at the channel level.

=== "Text command"

    `c>permissions channelall <channel> <is_allowed>`

=== "Slash command"

    `/permissions channelall channel:<channel> is_allowed:<True|False>`

<h3>Options</h3>

- `channel`: The channel to apply this permission to.
- `is_allowed`: Whether the command is enabled or not.

## permissions member

Enable or disable a command or group at the member level.

=== "Text command"

    `c>permissions member <command_or_group> <member> <is_allowed>`

=== "Slash command"

    `/permissions member command_or_group:<command_or_group> member:<member> is_allowed:<True|False>`

<h3>Options</h3>

- `command_or_group`: The command or group name.
- `member`: The member to apply this permission to.
- `is_allowed`: Whether the command is enabled or not.

## permissions memberall

Enable or disable all commands at the member level.

=== "Text command"

    `c>permissions memberall <member> <is_allowed>`

=== "Slash command"

    `/permissions memberall member:<member> is_allowed:<True|False>`

<h3>Options</h3>

- `member`: The member to apply this permission to.
- `is_allowed`: Whether the command is enabled or not.
