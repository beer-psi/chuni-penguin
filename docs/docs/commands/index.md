# Commands

chuni penguin supports both text commands (also known as prefix commands) and slash
commands.

- Text commands are more expressive and occasionally support more features, however
there is a small learning curve.
- Slash commands are more intuitive and integrates well with Discord, providing
helpful descriptions and autocompletions.

This documentation will cover both command types. Some commands are only available
as text commands. Command aliases are only usable on text commands.

## Prefix

Text commands must start with a prefix in order to be recognized by the bot. The
documentation uses the default prefix, `c>`, but server administrators may choose to
change this in their own servers. To view the current prefix, use the `/prefix` slash
command, or mention the bot:

```
@chuni penguin prefix
```

## Text command conventions

Text commands are heavily inspired by Unix command line programs. If you wish to use
text commands, please make sure you've familiarized yourself with the conventions before
checking out the documentation:

### Positional arguments

Positional arguments must be specified **in order**. There are two main types of
positional arguments:

- `<argument>`, `ARGUMENT`: The argument named `argument` is required. Do not include
the opening and closing brackets. Putting the argument in quotes is required when the
argument has `"multiple words"`.
- `[argument]`: The argument named `argument` is optional. Do not include the opening
and closing brackets. Putting the argument in quotes is required when the argument has
`"multiple words"`.

```
c>alias add <song_title_or_alias> <added_alias> [global_alias=False]
```

- `<argument...>`: Similar to `<argument>`, but quoting is not required.
- `[argument...]`: Similar to `[argument...]`, but quoting is not required.

```
c>scores <query ...>
```

### Options

Options can be specified in any order.

- `[-o]`, `[--option]`: A true/false option. Specify the flag to enable the option, omit
the flag to disable the option.
- `[-o <option>]`, `[--option <option>]`: An option. Specify the option name, including
the leading dashes, then specify the option's value. Quoting is required unless
there are ellipses, just like `<argument>` and `<argument...>`.

```
c>top [-d <difficulty>] [-k]
```

### User

A user can be specified using all their identifiers, in order of:

- User ID (`810818056171421726`)
- Mention/ping (`@beerpsi`)
- Username (`beerpsi_`)
- Global display name (`beerpsi`)
- Server nickname (`wo cow`)
