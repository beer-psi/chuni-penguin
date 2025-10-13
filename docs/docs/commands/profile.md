## avatar

View the user's penguin avatar.

=== "Text command"

    `c>avatar [user]`

=== "Slash command"

    `/avatar [user:<user>]`

<h3>Options</h3>

- `user`: <small>(default: you)</small> The user to view the penguin avatar of.

## chunithm

View the user's CHUNITHM profile.

=== "Text command"

    `c>chunithm [-k] [user]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to view the profile of.
    - `-k, --kamaitachi`: View the user's CHUNITHM profile on Kamaitachi, if available.

=== "Slash command"

    `/avatar [user:<user>] [kamaitachi:<True|False>]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to view the profile of.
    - `kamaitachi`: <small>(default: False)</small> View the user's CHUNITHM profile on
    Kamaitachi, if available.

## config

Adjust or view your default configuration for commands.

=== "Text command"

    `c>config <key> [value]`

=== "Slash command"

    `/config key:<key> [value:<value>]`

<h3>Options</h3>

- `key`: The option you want to change or view.
- `value`: The value to change the option to. Leave blank to see the current value for
the given option.

Currently, the options available are:

- `synthesis-alt-jacket`: Changes the jacket art for the song "Synthesis." whereever
applicable. The possible options are `none` (black background), `default`
(use CHUNITHM's jacket art), `cytus2`, `vividstasis`, `musedash`, and `musicdiver`.
- `privacy`: Do not allow other users to view your profile and scores using the bot.
You can still use commands, but to others it will seem like you're not logged in.
The possible options are `true` (enabled) and `false` (disabled).

## loginbonus

View your current login bonus progress on CHUNITHM International.

=== "Text command"

    `c>loginbonus`

=== "Slash command"

    `/loginbonus`

## rename

Change your player name on CHUNITHM International.

=== "Text command"

    `c>rename <new_name...>`

=== "Slash command"

    `/avatar new_name:<new_name>`

<h3>Options</h3>
- `new_name`: The player name to change to. All the usual restrictions apply: 8
characters or fewer, only some special characters allowed.
