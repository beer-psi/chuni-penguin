## chuni penguin

[![Deploy](https://github.com/beer-psi/chuni-penguin/actions/workflows/deploy.yaml/badge.svg)](https://github.com/beer-psi/chuni-penguin/actions/workflows/deploy.yaml)
[![State-of-the-art Shitcode](https://img.shields.io/static/v1?label=State-of-the-art&message=Shitcode&color=7B5804)](https://github.com/trekhleb/state-of-the-art-shitcode)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Support server](https://dcbadge.limes.pink/api/server/https://discord.gg/DyYrrzQQ9W)](https://discord.gg/DyYrrzQQ9W)

Discord bot for CHUNITHM International version.

I have a hosted instance that you can invite
[here](https://discord.com/oauth2/authorize?client_id=1091948342101155950&scope=bot+applications.commands&permissions=274877983744),
though uptime is sometimes flaky.

### Notice

I will not be actively developing the bot anymore. There's not much left I think
the bot actually needs, and my motivation has been slowly waning to implement
them. I'll still fix any reported bugs and review any PRs.

### Features

- [x] Player data
- [x] Recent scores (including detailed judgements)
- [x] Best scores
  - [x] b30 and recent 10
  - [x] by song
- [x] Comparing scores
- [x] Song information
  - [x] sdvx.in integration
- [x] Search tracks by internal level
- [x] Calculate play rating
- [x] Slash command support
- [x] Minigames (song quiz)

### Setup instructions

0. Install [Rye](https://rye.astral.sh/guide/installation/)
1. Copy `bot.example.ini` to `bot.ini` and fill in values based on the comments.
2. Run `rye sync` to install dependencies.
3. Run `python dbutils.py create` to create the database. You may need to
   activate the virtualenv first if you had a previous Python installation not
   managed by rye.
4. Run `python dbutils.py update chunirec` to populate the song database. For
   this to work, `credentials.chunirec_token` **must** be set in `bot.ini`. A
   pre-populated database is also provided
   [here](https://nightly.link/beer-psi/chuni-penguin/workflows/test_creating_db.yaml/trunk/database.zip),
   for your convenience.
5. `python bot.py`

### Credits

Thanks to these projects for making this bot possible and less miserable to
make:

- [Chunirec DB](https://db.chunirec.net) from
  [chunirec](https://twitter.com/chunirec)
- [arcade-songs](https://arcade-songs.zetaraku.dev) from
  [Raku Zeta](https://github.com/zetaraku)
- [CHUNITHM song alias list](https://github.com/lomotos10/GCM-bot/blob/main/data/aliases/en/chuni.tsv)
  from [lomotos10](https://github.com/lomotos10)
- [Tukkun](https://github.com/tukkun1995) for breaking my bot in unthinkable
  ways (aside from being
  [a contributor](https://github.com/beer-psi/chuni-penguin/pulls?q=is%3Apr+author%3Atukkun1995+)),
  as well as taking the time to add all the song aliases.

Thanks to all the
[contributors](https://github.com/beer-psi/chuni-penguin/graphs/contributors)
who took part.

<details>
    <summary>Donation</summary>

chuni-penguin is entirely free (as in both free beer and free speech), but you
can monetarily support its development by donating through
[Ko-fi](https://ko-fi.com/beerpsi_) or directly if you live in Vietnam:

- Bank: Vietcombank
- Account: beerpsi

Thank you to everyone who donated:

- [Tukkun](https://github.com/tukkun1995)

</details>
