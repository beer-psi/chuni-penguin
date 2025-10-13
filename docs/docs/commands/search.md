## alias add

<small>(aliases: `addalias`)</small>

Add an alias to an existing song. This alias can be used in the server that the command
was invoked in.

=== "Text command"

    `c>alias add <song_title_or_alias> <added_alias> [global_alias]`

=== "Slash command"

    `/alias add song_title_or_alias:<song_title_or_alias> added_alias:<added_alias> [global_alias:<True|False>]`

<h3>Options</h3>

- `song_title_or_alias`: The title or an existing alias of the song.
- `added_alias`: The alias to add.
- `global_alias`: <small>(default: False)</small> Whether to apply the alias to all
servers. Only a few users can do this.

## alias list

<small>(aliases: `listalias`, `listaliases`, `aliases`)</small>

List all global and server aliases for the song.

=== "Text command"

    `c>alias list <query...>`

=== "Slash command"

    `/alias list query:<query>`

<h3>Options</h3>

- `query`: The title of the song. You don't have to be exact; try things out!

## alias remove

<small>(aliases: `removealias`, `alias delete`)</small>

Remove a song alias for the server the command was invoked in.

The alias creator can always delete their own aliases. If someone has the Manage Server
permissions then they can also delete it. Bot owners can delete any alias.

=== "Text command"

    `c>alias remove <removed_alias...>`

=== "Slash command"

    `/alias remove removed_alias:<removed_alias>`

<h3>Options</h3>

- `removed_alias`: The alias to remove.


## courses

Get a list of all courses.

If you are logged in to CHUNITHM-NET, this also displays your course records.

=== "Text command"

    `c>courses`

=== "Slash command"

    `/courses`

## find

Find charts by level or chart constant.

=== "Text command"

    `c>find <level>`

=== "Slash command"

    `/find level:<level>`

<h3>Options</h3>

- `level`: The level or chart constant to search for.

## info

Search for a song.

=== "Text command"

    `c>info [-d] <query...>`

    <h3>Options</h3>

    - `query`: The title of the song. You don't have to be exact; try things out!
    - `-d, --detailed`: View the charter and notecount for each chart in the song.

=== "Slash command"

    `/info query:<query> [detailed:<True|False>]`

    <h3>Options</h3>

    - `query`: The title of the song. You don't have to be exact; try things out!
    - `detailed`: <small>(default: False)</small> View the charter and notecount for
    each chart in the song.
