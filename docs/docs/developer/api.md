The base URL of the official instance is [https://chunithm.beerpsi.cc](https://chunithm.beerpsi.cc).

## List songs

`GET /songs`

Retrieve the list of songs available on the instance.

Returns a list of songs, each song having these properties:

| Property        | Type                            | Description                                                   |
|-----------------|---------------------------------|---------------------------------------------------------------|
| `id`            | integer                         | The song ID.                                                  |
| `chunirec_id`   | string \| null                  | The ID of the song on [chunirec DB](https://db.chunirec.net). |
| `title`         | string                          | The title of the song.                                        |
| `aliases`       | string[]                        | List of global aliases assigned to this song.                 |
| `artist`        | string                          | The artist of the song.                                       |
| `genre`         | string                          | The genre name the song belongs to.                           |
| `release_date`  | string                          | An ISO8601 date string of when the song was released.         |
| `version`       | string                          | The CHUNITHM version the song was released in.                |
| `jacket_url`    | string                          | A URL to the song's jacket art.                               |
| `bpm`           | [BPM](#bpm)                     | The song's mininmum, maximum and primary BPMs.                |
| `availablility` | [Availablility](#availablility) | The song's availablility in different regions of the game.    |
| `charts`        | [Chart](#chart)[]               | The song's charts.                                            |

### BPM

| Property        | Type          | Description             |
|-----------------|---------------|-------------------------|
| `min`           | number        | The song's minimum BPM. |
| `max`           | number        | The song's maximum BPM. |
| `mode`          | number        | The song's primary BPM. |

### Availablility

| Property        | Type          | Description                                                      |
|-----------------|---------------|------------------------------------------------------------------|
| `intl`          | boolean       | Whether the song is available in CHUNITHM International version. |
| `jp`            | boolean       | Whether the song is available in CHUNITHM Japan version.         |

### Chart

| Property        | Type                      | Description                                                                       |
|-----------------|---------------------------|-----------------------------------------------------------------------------------|
| `difficulty`    | string                    | The chart's difficulty: `BAS`/`ADV`/`EXP`/`MAS`/`ULT`/`WE`.                       |
| `level`         | string                    | The chart's in-game level.                                                        |
| `const`         | number                    | The chart's chart constant/internal level.                                        |
| `charter`       | string                    | Name of the charter who made this chart.                                          |
| `version`       | string \| null            | The version the chart was released in, if it's different from the song's version. |
| `sdvxin_url`    | string \| null            | A link to the chart's chart view on [sdvx.in](https://sdvx.in/chunithm.html).     |
| `notecounts`    | [Notecounts](#notecounts) | The chart's notecount data.                                                       |

#### Notecounts

| Property        | Type            | Description                                                          |
|-----------------|-----------------|----------------------------------------------------------------------|
| `total`         | integer \| null | The chart's total number of notes.                                   |
| `tap`           | integer \| null | The chart's number of tap notes.                                     |
| `hold`          | integer \| null | The chart's number of hold notes, including hold ticks.              |
| `slide`         | integer \| null | The chart's number of slide notes, including slide ticks.            |
| `air`           | integer \| null | The chart's number of air notes, including air hold/air slide ticks. |
| `flick`         | integer \| null | The chart's number of flick notes.                                   |

## Get invite URL

`GET /invite`

Redirects to the instance's Discord invite link.

## Link CHUNITHM-NET account

`POST /login`

Link the provided CHUNITHM-NET access token with the account assigned to the login code.
A login code can be obtained using the [`login` command](../commands/authentication.md#login).

Content types: `application/x-www-form-urlencoded`, `multipart/form-data`,
`application/json`

Parameters:

| Property | Type   | Description                                                                            |
|----------|--------|----------------------------------------------------------------------------------------|
| `otp`    | string | The login code. A string of 6 digits.                                                  |
| `clal`   | string | The CHUNITHM-NET access token. Must be a string containing 64 alphanumeric characters. |

Returns a HTML page indicating if the login was successful or not.

## Kamaitachi OAuth callback

`GET /kamaitachi/oauth`

Standard OAuth callback endpoint. The `context` is expected to be populated with the
authenticating user's Discord user ID.

## Get Kamaitachi profile picture/banner

`GET /kamaitachi/users/:user_id/pfp/:hash`<br>
`GET /kamaitachi/users/:user_id/banner/:hash`

This is equivalent to these Kamaitachi CDN fetches:

- `https://cdn-kamai.tachi.ac/users/:user_id/pfp-:hash`
- `https://cdn-kamai.tachi.ac/users/:user_id/banner-:hash`

but some processing is done to respond with the correct content type (instead of
`application/octet-stream`). If this doesn't matter for your use case, you should hit
Kamaitachi CDN directly.
