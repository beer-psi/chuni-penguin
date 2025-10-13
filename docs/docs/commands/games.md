## guess jacket, guess audio, guess voice

Starts a song guessing game:

- `guess jacket`: Guess the song from a part of its jacket art.
- `guess audio`: Guess the song from a music clip, sent as a voice message.
- `guess voice`: **:warning: Server only**. Guess the song from a music clip played in a voice call.

=== "Text command"

    `c>guess <jacket|audio|voice> [options]`

    <h3>Options</h3>

    - `-d, --difficulty <difficulty>`: <small>(default: BASIC)</small> The difficulty
    of the game. One of five values `BASIC`, `ADVANCED`, `EXPERT`, `MASTER`
    and `ULTIMA`. Common shorthands such as `BAS` are also supported.
    - `-q, --questions <questions>`: <small>(default: 20)</small> The number of
    questions for this game. There is no upper limit, but note that games automatically
    stop after 3 questions of inactivity.
    - `-s, --score <score>`: <small>(default: None)</small> The score a player must
    reach for the game to automatically end early.
    - `-t, --time <time>`: <small>(default: depends on difficulty)</small> Time in
    seconds to answer each question.
    - `-w, --wrong <count>`: <small>(default: None)</small> Number of questions to
    answer incorrectly before the game is stopped.
    - `-g, --genre <genres...>`: <small>(default: None)</small> Limit song pool to the
    given genres. Specify multiple genres with spaces, e.g. `-g niconico original`.
    **Games played with this option will not be counted towards the leaderboard.**
    - `-v, --volume <volume>`: <small>(default: 15)</small> **(voice only)** Sets the
    volume of the bot, as a percentage between 1 and 100. This can get extremely loud.
    - `-h, --hardcore`: Hardcore mode, each player gets one chance to answer each
    question correctly.

    <h3>Examples</h3>

    - Enable hardcore mode: `c>guess audio -h`
    - 15 questions on EXPERT difficulty: `c>guess jacket -q 15 -d EXPERT`

The difficulties and times per question for each game mode is determined as follow:

=== "guess jacket"

    - BASIC: 90x90 crop and no filters.
    - ADVANCED: 75x75 crop and no filters.
    - EXPERT: 75x75 crop and images may be rotated 90/180/270 degrees.
    - MASTER: 60x60 crop and images may be rotated 90/180/270 degrees.
    - ULTIMA: 60x60 crop, colors may be inverted, images may be rotated 90/180/270
    degrees.

    The default time for each question is always 20 seconds, regardless of difficulty.

=== "guess audio/guess voice"

    - BASIC: 15 seconds of the song played.
    - ADVANCED: 10 seconds of the song played.
    - EXPERT: 7 seconds of the song played.
    - MASTER: 4 seconds of the song played.
    - ULTIMA: 1 second of the song played.

    The default time for each question is the audio length, plus 5 seconds.

## guess leaderboard

**:warning: Server only**

View the score leaderboard for the song guessing game in the current
server.

=== "Text command"

    `c>guess leaderboard`

## guess reset

**:warning: Server only**<br>
**:warning: Required permissions: Manage Server**

Resets the leaderboard for the current server.

=== "Text command"

    `c>guess reset`

## volume

Set the bot's volume for the current voice guessing game.

=== "Text command"

    `c>volume <volume>`

## skip

Skips a state of an ongoing guessing game.

You can use this to skip a question, but also skip any waiting times, such as the
starting 5-second wait.

=== "Text command"

    `c>skip`

## stop

Stops the currently running guessing game.

=== "Text command"

    `c>stop`
