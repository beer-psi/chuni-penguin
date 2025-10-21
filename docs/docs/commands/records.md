## best50

<small>(aliases: `b50`, `best30`, `b30`)</small>

View the rating breakdown of a player.

=== "Text command"

    `c>best50 [-c] [-k] [-n] [user]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to get the rating breakdown for.
    - `-c, --classic`: View the breakdown using Discord embeds instead of generating
    an image.
    - `-k, --kamaitachi`: View the user's breakdown on Kamaitachi, if available.
    - `-n, --new-rating`: When viewing on Kamaitachi, calculate a best30+new20 split
    instead of best50.

=== "Slash command"

    `/best50 [user:<user>] [classic:<True|False>] [kamaitachi:<True|False>] [new-rating:<True|False>]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to get the rating breakdown for.
    - `classic`: <small>(default: False)</small> View the breakdown using Discord embeds
    instead of generating an image.
    - `kamaitachi`: <small>(default: False)</small> View the user's breakdown on
    Kamaitachi, if available.
    - `new-rating`: <small>(default: False)</small> When viewing on Kamaitachi,
    calculate a best30+new20 split instead of best50.

## compare

<small>(aliases: `c`, `mog`, `gap`)</small>

Compare a user's score to a recent chart or score card.

By default, the most recent message containing a chart or score card is chosen. If the
message contains multiple cards, you will be prompted to select one.

**Text command only:** You can choose another message by replying to the message when
invoking the command.

=== "Text command"

    `c>compare [-k] [user]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to get the score of.
    - `-k, --kamaitachi`: View the user's score on Kamaitachi, if available.

=== "Slash command"

    `/compare [user:<user>] [kamaitachi:<True|False>]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to get the score of.
    - `kamaitachi`: <small>(default: False)</small> View the user's score on Kamaitachi,
    if available.

## leaderboard

<small>(aliases: `lb`)</small>

View the leaderboard for a chart.

=== "Text command"

    `c>leaderboard [-k] <difficulty> <query...>`

    <h3>Options</h3>

    - `difficulty`: The difficulty of the chart.
    - `query`: The title of the song. You don't have to be exact; try things out!
    - `-k, --kamaitachi`: View the Kamaitachi leaderboard for the song.

=== "Slash command"

    `/leaderboard difficulty:<difficulty> query:<query> [kamaitachi:<True|False>]`

    <h3>Options</h3>

    - `difficulty`: The difficulty of the chart.
    - `query`: The title of the song. You don't have to be exact; try things out!
    - `kamaitachi`: <small>(default: False)</small> View the Kamaitachi leaderboard for
    the song.

## recent

<small>(aliases: `rs`)</small>

View a user's most recent scores.

=== "Text command"

    `c>recent [-k] [user]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to get recent scores of.
    - `-k, --kamaitachi`: View the user's recent scores on Kamaitachi, if available.

=== "Slash command"

    `/recent [user:<user>] [kamaitachi:<True|False>]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to get recent scores of.
    - `kamaitachi`: <small>(default: False)</small> View the user's recent scores on
    Kamaitachi, if available.

## scores

<small>(aliases: `score`)</small>

Get a user's scores for a specific song, or [compare](#compare) the user's scores with
another score.

=== "Text command"

    `c>scores [-k] [user] [query...]`

    <h3>Options</h3>

    - `query`: The title of the song. You don't have to be exact; try things out! If a
    query was not specified, the command works the same as [compare](#compare).
    - `user`: <small>(default: you)</small> The user to get the score of.
    - `-k, --kamaitachi`: View the user's score on Kamaitachi, if available.

=== "Slash command"

    `/scores query:<query> [user:<user>] [kamaitachi:<True|False>]`

    <h3>Options</h3>

    - `query`: The title of the song. You don't have to be exact; try things out!
    - `user`: <small>(default: you)</small> The user to get the score of.
    - `kamaitachi`: <small>(default: False)</small> View the user's score on Kamaitachi,
    if available.

## top

Get a user's best scores for a specified set of charts.

=== "Text command"

    `c>top [-k] [-d <difficuly>] [-g <genre>] [-r <rank>] [-s <sort...>] [user] [level]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to get the score of.
    - `level`: <small>(default: None)</small> Get scores from the specified level, from
    1 to 15+. Chart constants are also supported.
    - `-d, --difficulty`: Get scores from the specified difficulty. Must be one of
    `BASIC`, `ADVANCED`, `EXPERT`, `MASTER`, `ULTIMA` or `WE`, or any common
    abbreviations such as `MAS`.
    - `-g, --genre`: Get scores for songs in the specified genre.
    - `-r, --rank`: Get scores from the specified rank.
    - `-s, --sort`: Sort scores by the specified metric. You can specify multiple
    metrics, e.g. `-s score clear_lamp`. You can optionally add `+` or `-` after a
    metric to sort in ascending or descending order, e.g. `score+`. The default is to
    sort by rating, then score, then overpower, then note lamp, then clear lamp, all in
    descending order. Supported options are:
        - `score`: Sort by score.
        - `rating`: Sort by calculated play rating. Might not work if there are unknown
        songs.
        - `overpower`: Sort by calculated raw overpower value.
        - `overpower_percent`: Sort by calculated overpower percentage.
        - `note_lamp`: Sort by note lamp (also known as combo lamp, e.g. FULL COMBO/ALL
        JUSTICE).
        - `clear_lamp`: Sort by clear lamp (FAILED, CLEAR, HARD, BRAVE, ABSOLUTE,
        CATASTROPHY).
    - `-k, --kamaitachi`: View the user's scores on Kamaitachi, if available.

=== "Slash command"

    `/top [user:<user>] [level:<level>] [difficulty:<difficulty>] [genre:<genre>] [rank:<rank>] [sort:<sort>] [sort_order:<ascending|descending>] [kamaitachi:<True|False>]`

    <h3>Options</h3>

    - `user`: <small>(default: you)</small> The user to get the score of.
    - `level`: <small>(default: None)</small> Get scores from the specified level, from
    1 to 15+.
    - `difficulty`: <small>(default: None)</small> Get scores from the specified
    difficulty.
    - `genre`: <small>(default: None)</small> Get scores for songs in the specified
    genre.
    - `rank`: <small>(default: None)</small> Get scores from the specified rank.
    - `sort`: <small>(default: rating)</small> Sort scores by the specified metric.
    - `sort_order`: <small>(default: descending)</small> Sort scores in ascending or
    descending order.
    - `kamaitachi`: <small>(default: False)</small> View the user's scores on
    Kamaitachi, if available.
