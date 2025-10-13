## login

Link your CHUNITHM-NET International account with the bot.

=== "Text command"

    `c>login [clal]`

=== "Slash command"

    `/login [clal:<clal>]`

<h3>Options</h3>

- `clal`: <small>(default: None)</small> The cookie value to log in with. If you don't
know what this is, simply run the command without any parameters, and you will get
guided through the login process.

## logout

Unlinks your CHUNITHM-NET International account from the bot.

=== "Text command"

    `c>logout [invalidate]`

=== "Slash command"

    `/logout [invalidate:<invalidate>]`

<h3>Options</h3>

- `invalidate`: <small>(default: False)</small> Also logs out from CHUNITHM-NET,
invalidating the token. The default is False, which only deletes the token from the
database, but the token remains valid.

## token

View the CHUNITHM-NET International token linked with the bot. May be useful for linking
with other maimai DX/CHUNITHM bots.

=== "Text command"

    `c>token`

    **:warning: Direct messages only**

=== "Slash command"

    `/token`
