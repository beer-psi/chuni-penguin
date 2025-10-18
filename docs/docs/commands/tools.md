## anmitsu

<small>(aliases: `rub`)</small>

Determine whether you can get JUSTICE / JUSTICE CRITICAL through ["anmitsu" technique](https://chunithm.org/intermediate/tech/#anmitsu).

=== "Text command"

    `c>anmitsu <bpm> [note_density]`

=== "Slash command"

    `/anmitsu bpm:<bpm> [note_density:<note_density>]`

<h3>Options</h3>

- `bpm`: The BPM of the song. You can use the [`info` command](./search.md#info) to find
this.
- `note_density`: <small>(default: 16)</small> The denominator for the beat divisor.
For example, 16 means 1/16, or 1 measure = 16 notes.

## border

Display the number of permissible JUSTICE, ATTACK and MISS to achieve specific ranks on
a chart.

The values are based on realistic JUSTICE:ATTACK:MISS ratios and are for reference only.
In terms of scoring, the score decrease from 1 ATTACK is equivalent to 51 JUSTICE, and 1
MISS is equivalent to 101 JUSTICE.

=== "Text command"

    `c>border <difficulty> <query...>` **OR** `c>border <notecount>`

    <h3>Options</h3>

    - `difficulty`: The difficulty of the chart. Must be one of `BASIC`, `ADVANCED`,
    `EXPERT`, `MASTER`, `ULTIMA` or `WE`, or any common abbreviations such as `MAS`.
    - `query`: The title of the song. You don't have to be exact; try things out!
    - `notecount`: Calculate the border for the specific notecount.

=== "Slash command"

    `/border difficulty_or_notecount:<difficulty_or_notecount> [query:<query>]`

    <h3>Options</h3>

    - `difficulty_or_notecount`: The difficulty of the chart. Alternatively, enter a
    notecount here to get the border for that specific notecount.
    - `query`: The title of the song. You don't have to be exact; try things out!

## calculate

Calculate rating and over power from score and chart constant.

=== "Text command"

    `c>calculate <score> [chart_constant]`

=== "Slash command"

    `/calculate score:<score> [chart_constant:<chart_constant>]`

<h3>Options</h3>
- `score`: The score to calculate play rating and over power from.
- `chart_constant`: The chart constant of the chart. You can use the [`info` command](./search.md#info)
to find this.

## chart

Renders a chart view from [sdvx.in](https://sdvx.in/chunithm.html) for a given song and difficulty.

=== "Text command"

    `c>chart <difficulty> <query...>`

    <h3>Options</h3>

    - `difficulty`: The difficulty of the chart. Must be one of `BASIC`, `ADVANCED`,
    `EXPERT`, `MASTER`, `ULTIMA` or `WE`, or any common abbreviations such as `MAS`.
    - `query`: The title of the song. You don't have to be exact; try things out!

=== "Slash command"

    `/chart difficulty:<difficulty> query:<query>`

    <h3>Options</h3>

    - `difficulty`: The difficulty of the chart.
    - `query`: The title of the song. You don't have to be exact; try things out!


## const

Calculate rating and over power achieved with various scores based on chart constant.

=== "Text command"

    `c>const <chart_constant> [mode]`

=== "Slash command"

    `/const chart_constant:<chart_constant> [mode:<default|aj>]`

<h3>Options</h3>

- `chart_constant`: The chart constant. You can use the [`info` command](./search.md#info)
to find this.
- `mode`: <small>(default: default)</small> Sets the display mode:
    - `default`: Display rating information only
    - `aj`: Display OP information for ALL JUSTICE only

## odex

Read the Codex.

=== "Text command"

    `c>odex`

=== "Slash command"

    `/codex`

## random

<small>(aliases: `rand`)</small>

Get random charts based on the given level/course/chart constant.

=== "Text command"

    `c>random <level> [count]`

=== "Slash command"

    `/random level:<level> [count:<count>]`

<h3>Options</h3>

- `level`: Level to search for. Can be a level (13+), a chart constant (13.5), a level
range (13.5-13.8), or a course class (`i`, `ii`, `iii`, `iv`, `v`, `inf`, `random`,
`wallpanic`, `sibyl`).
- `count`: <small>(default: 3)</small> Number of charts to return. Must be between 1
and 10. Not respected when rolling a random course.

## rating

Calculate score required to achieve the specified play rating at different chart
constants.

=== "Text command"

    `c>rating <rating>`

=== "Slash command"

    `/rating rating:<rating>`

<h3>Options</h3>

- `rating`: Play rating to achieve.

## recommend

Get random chart recommendations with target scores based on your rating.

Please note that recommended charts are generated randomly and are independent of your high scores.

=== "Text command"

    `c>recommend [count] [target_rating]`

=== "Slash command"

    `/recommend [count:<count>] [target_rating:<target_rating>]`

<h3>Options</h3>

- `count`: <small>(default: 3)</small> Number of charts to return. Must be between 1 and 4.
- `target_rating`: Your target play rating. If not provided, uses your best30/best50
average if you have accounts linked. Otherwise, this parameter is required.

## whatif

Calculate rating gained if you achieve a play with the given play rating.

=== "Text command"

    `c>whatif <play_rating> [current_play_rating]`

=== "Slash command"

    `/whatif play_rating:<play_rating> [current_play_rating:<current_play_rating>]`

<h3>Options</h3>

- `play_rating`: The play rating you would achieve.
- `current_play_rating`: The current play rating of the chart if it is already in your
best 50 scores. Leave blank if the chart is currently not included in your
best 50 scores.
