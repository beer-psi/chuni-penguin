import asyncio
import contextlib
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Optional

import discord
import httpx
import httpx_aiohttp
import msgspec
from discord.ext import commands
from discord.ext.commands import Context
from sqlalchemy import select

from chuni_penguin.config import config
from chuni_penguin.context import PenguinContext
from chuni_penguin.database import Cookie
from chuni_penguin.logging import logged_prefix_command, logger
from chuni_penguin.networks.consts import KEY_SONG_ID
from chuni_penguin.networks.kamaitachi import (
    KTBatchManualResponse,
    KTImportPollStatusCompleted,
    KTImportPollStatusOngoing,
    KTImportPollStatusResponse,
    KTResponse,
    KTStatusResponse,
    convert_to_kt_batch_manual,
)
from chuni_penguin.networks.types import Difficulty, PersonalBest, RecentScore

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot
    from chuni_penguin.cogs.botutils import UtilsCog
    from chuni_penguin.cogs.events import EventsCog


class ReprocessOrphanSummary(msgspec.Struct, rename="camel"):
    processed: int
    failed: int
    success: int
    removed: int


class KamaitachiCog(commands.Cog, name="Kamaitachi"):
    def __init__(self, bot: "ChuniBot") -> None:
        if (kt_client_id := config.credentials.kamaitachi_client_id) is None:
            msg = "Kamaitachi client ID is not set"
            raise ValueError(msg)

        kt_client_secret = None
        if (
            bot.app is not None
            and (kt_client_secret := config.credentials.kamaitachi_client_secret)
            is None
        ):
            msg = "Kamaitachi client secret is not set"
            raise ValueError(msg)

        self.bot = bot
        self.utils: "UtilsCog" = bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]

        self.kt_client_id = kt_client_id
        self.kt_client_secret = kt_client_secret
        self.user_agent = f"ChuniPenguin (https://github.com/Rapptz/discord.py {discord.__version__}) Python/{sys.version_info[0]}.{sys.version_info[1]} httpx/{httpx.__version__}"

    @commands.hybrid_group("kamaitachi", aliases=["kt"], hidden=True)
    @logged_prefix_command
    async def kamaitachi(self, ctx: Context):
        pass

    async def _verify_and_login(self, token: str) -> Optional[str]:
        async with httpx.AsyncClient(
            transport=httpx_aiohttp.AIOHTTPTransport(retries=5)
        ) as client:
            client.headers["User-Agent"] = self.user_agent
            client.headers["Authorization"] = f"Bearer {token}"

            resp = await client.get("https://kamai.tachi.ac/api/v1/status")
            data = msgspec.json.decode(resp.content, type=KTStatusResponse)

        if not data.success:
            return data.description

        assert data.body is not None

        if data.body.whoami is None:
            return "The provided API token is not bound to any user."

        permissions = data.body.permissions

        if "submit_score" not in permissions or "customise_score" not in permissions:
            return (
                "The provided API token is missing permissions.\n"
                "Ensure that the token has permissions `submit_score` and `customise_score`."
            )

        return None

    @kamaitachi.command("link", aliases=["login"])
    @logged_prefix_command
    async def kamaitachi_link(self, ctx: PenguinContext, token: Optional[str] = None):
        """Link with your Kamaitachi account.

        You must enable direct messages with the bot. Alternatively, use the slash
        command variant, `/kamaitachi link`.

        Parameters
        ----------
        token: Optional[str]
            IGNORE IF YOU DON'T KNOW WHAT THIS IS FOR. You will get a URL to link your account.
        """

        if ctx.interaction is not None and ctx.guild is not None:
            await ctx.interaction.response.defer(ephemeral=True, thinking=True)

        async with self.bot.begin_db_session() as session:
            query = select(Cookie).where(Cookie.discord_id == ctx.author.id)
            cookie = (await session.execute(query)).scalar_one_or_none()

        channel = (
            ctx.author.dm_channel
            if ctx.author.dm_channel
            else await ctx.author.create_dm()
        )

        if ctx.guild is not None and ctx.interaction is None:
            please_delete_message = ""

            if token is not None:
                try:
                    await ctx.message.delete()
                except discord.errors.HTTPException:
                    await logger.awarning(
                        "Could not delete message with token exposed",
                        tag="failed_delete_message_exposing_keys",
                        guild_id=ctx.guild.id if ctx.guild else None,
                        channel_id=ctx.channel.id,
                        user_id=ctx.author.id,
                        message_id=ctx.message.id,
                    )

                    please_delete_message = (
                        "You sent the command in a public channel and included your "
                        "Kamaitachi API key, which leaves your Kamaitachi account at risk. "
                        "Please delete the command yourself, as I do not have sufficient "
                        "permissions to do it. "
                        "Please also practice some internet safety and don't send credentials "
                        "in public places.\n\n"
                        "Visit https://kamai.tachi.ac/u/me/integrations to revoke your "
                        "API key."
                    )

            await ctx.respond_or_edit(
                f"Login instructions have been sent to your DMs. "
                f"(please **enable Privacy Settings -> Direct Messages** if you haven't received it.)\n\n{please_delete_message}"
            )
        elif token is not None:
            result = await self._verify_and_login(token)
            if result is not None:
                raise commands.BadArgument(result)

            content = "Successfully linked with Kamaitachi."

            async with self.bot.begin_db_session() as session, session.begin():
                if cookie is None:
                    cookie = Cookie(
                        discord_id=ctx.author.id, cookie="", kamaitachi_token=token
                    )
                    session.add(cookie)
                else:
                    cookie.kamaitachi_token = token
                    await session.merge(cookie)

                    if cookie.cookie:
                        content += (
                            f"\nYou can now use `{ctx.clean_prefix}kamaitachi sync` to sync your recent scores.\n"
                            "\n"
                            f"**It is recommended that you run `{ctx.clean_prefix}kamaitachi sync` to sync your recent scores first, "
                            f"before syncing your personal bests with `{ctx.clean_prefix}kamaitachi sync pb`.**"
                        )

            return await ctx.reply(content=content, mention_author=False)

        embed = discord.Embed(
            title="Link with Kamaitachi",
            color=0xCA1961,
            description=(
                f"Retrive an API key from https://kamai.tachi.ac/client-file-flow/{self.kt_client_id} then "
                f"run `{'/' if ctx.interaction else config.bot.default_prefix}kamaitachi link <token>` in DMs."
            ),
        )
        if self.bot.app is not None:
            embed.description = (
                "Click this link to authenticate with Kamaitachi: "
                f"https://kamai.tachi.ac/oauth/request-auth?clientID={self.kt_client_id}&context={ctx.author.id}"
            )

        if ctx.guild is not None and ctx.interaction is None:
            with contextlib.suppress(discord.errors.Forbidden):
                return await channel.send(embed=embed)
        else:
            return await ctx.respond_or_edit(embed=embed)

    @kamaitachi.command("unlink", aliases=["logout"])
    @logged_prefix_command
    async def kamaitachi_unlink(self, ctx: Context):
        """Unlinks your Kamaitachi account."""

        async with self.bot.begin_db_session() as session:
            query = select(Cookie).where(Cookie.discord_id == ctx.author.id)
            cookie = (await session.execute(query)).scalar_one_or_none()

        if cookie is None or cookie.kamaitachi_token is None:
            msg = "You are not linked with Kamaitachi."
            raise commands.CommandError(msg)

        cookie.kamaitachi_token = None

        async with self.bot.begin_db_session() as session:
            await session.merge(cookie)
            await session.commit()

        return await ctx.reply(
            content="Successfully unlinked with Kamaitachi.", mention_author=False
        )

    @kamaitachi.command("sync", aliases=["s"], extras={"invoke_on_edit": False})
    @logged_prefix_command
    async def kamaitachi_sync(
        self, ctx: PenguinContext, sync: Literal["recent", "pb"] = "recent"
    ):
        """Sync scores from CHUNITHM-NET International with Kamaitachi.

        If the import fails due to a network issue, the data is saved and will be
        imported next time this command is run.

        Parameters
        ----------
        mode: str
            What to sync with Kamaitachi. Supported values are `recent` and `pb`.
            Default is `recent`.
        """

        async with self.bot.begin_db_session() as session:
            query = select(Cookie).where(Cookie.discord_id == ctx.author.id)
            cookie = (await session.execute(query)).scalar_one_or_none()

        if cookie is None or not cookie.cookie.startswith("#LWP-Cookies-2.0"):
            msg = f"Please login with `{ctx.clean_prefix}login` first before syncing with Kamaitachi."
            raise commands.CommandError(msg)

        if cookie.kamaitachi_token is None:
            msg = f"You are not linked with Kamaitachi. DM me with `{'/' if ctx.interaction else config.bot.default_prefix}kamaitachi link` for instructions."
            raise commands.CommandError(msg)

        scores = []

        await ctx.respond_or_edit("Fetching scores from CHUNITHM-NET...")

        async with (
            ctx.bot.chunithm_networks.chunithm_net(
                ctx.author.id, cookie.cookie
            ) as chuni_client,
            ctx.bot.chunithm_networks.kamaitachi(
                cookie.kamaitachi_token
            ) as tachi_client,
        ):
            profile = await chuni_client.get_profile()
            scores: list[RecentScore | PersonalBest] = []

            if sync == "recent":
                recents = await chuni_client.get_recent_scores()

                for recent in recents:
                    if recent.difficulty == Difficulty.worlds_end:
                        continue

                    detailed_recent = await chuni_client.get_detailed_recent_score(
                        recent
                    )
                    scores.append(detailed_recent)

                    if len(scores) % 10 == 0 or len(scores) == len(recents):
                        await ctx.respond_or_edit(
                            f"Fetching recent scores from CHUNITHM-NET... {len(scores)}/{len(recents)}"
                        )
            elif sync == "pb":
                charts: set[tuple[int, Difficulty]] = set()

                for difficulty in Difficulty:
                    if difficulty == Difficulty.worlds_end:
                        # Kamaitachi does not accept WORLD'S END scores
                        continue

                    await ctx.respond_or_edit(f"Fetching {difficulty} scores...")

                    records = await chuni_client.get_personal_bests_by_difficulty(
                        difficulty
                    )

                    for record in records:
                        scores.append(record)
                        charts.add((record.extras[KEY_SONG_ID], difficulty))

                hidden_songs = await ctx.bot.database.songs.get_hidden_on_chuninet()

                if len(hidden_songs) > 0:
                    await ctx.respond_or_edit("Fetching hidden songs...")

                for hidden_song in hidden_songs:
                    records = await chuni_client.get_personal_bests_on_song(
                        hidden_song.id
                    )

                    for record in records:
                        if (record.extras[KEY_SONG_ID], record.difficulty) in charts:
                            continue

                        scores.append(record)
                        charts.add((record.extras[KEY_SONG_ID], record.difficulty))

            # all of these should have song IDs... i think
            await self.bot.database.personal_bests.upsert_personal_bests(
                ctx.author.id, chuni_client.NAME, scores
            )

            await ctx.respond_or_edit("Uploading scores to Kamaitachi...")

            # Insert the pending import into the database, then fetch everything
            # from the database into a single import
            await ctx.bot.database.pending_kamaitachi_imports.insert(
                ctx.author.id,
                msgspec.to_builtins(convert_to_kt_batch_manual(profile, scores)),
            )
            batch_manual = (
                await ctx.bot.database.pending_kamaitachi_imports.get_import_data(
                    ctx.author.id
                )
            )

            try:
                resp = await tachi_client._client.post(
                    "https://kamai.tachi.ac/ir/direct-manual/import",
                    content=msgspec.json.encode(batch_manual),
                    headers={
                        "Content-Type": "application/json",
                        "X-User-Intent": "true",
                    },
                )
                data = msgspec.json.decode(resp.content, type=KTBatchManualResponse)
            except Exception as e:  # noqa: BLE001
                events: "EventsCog" = ctx.bot.get_cog("Events")  # pyright: ignore[reportAssignmentType]
                embed, delete_after = await events._construct_error_embed(
                    ctx, ctx.command.name if ctx.command else None, e
                )

                if embed.description is None:
                    await logger.aexception(
                        "Unhandled exception in command",
                        tag="command_error",
                        command=ctx.command.qualified_name if ctx.command else None,
                        exc_info=e,
                    )
                    await events._submit_error_to_webhook(ctx, e)

                    embed.description = (
                        "There was an error submitting scores to Kamaitachi."
                    )

                embed.description += "\n\nYour scores are saved in the bot and will be submitted next time you run the command."
                await events._send_error(ctx, embed, delete_after=delete_after)
                return None

            # if we made it to here, kt should have received the import already
            await ctx.bot.database.pending_kamaitachi_imports.delete_all(ctx.author.id)

            if not data.success:
                return await ctx.respond_or_edit(
                    f"Failed to upload scores to Kamaitachi: {data.description}"
                )

            assert data.body is not None

            poll_url = data.body.url

            while True:
                resp = await tachi_client._client.get(poll_url)
                data = msgspec.json.decode(
                    resp.content, type=KTImportPollStatusResponse
                )

                if not data.success:
                    return await ctx.respond_or_edit(
                        f"Failed to upload scores to Kamaitachi: {data.description}"
                    )

                if isinstance(data.body, KTImportPollStatusOngoing):
                    if isinstance(data.body.progress, int):
                        await ctx.respond_or_edit(
                            f"Importing scores: {data.description}"
                        )
                    else:
                        await ctx.respond_or_edit(
                            (
                                f"Importing scores: {data.description}\n"
                                f"Progress: {data.body.progress.description}"
                            )
                        )
                    await asyncio.sleep(2)
                    continue

                if isinstance(data.body, KTImportPollStatusCompleted):
                    import_doc = data.body.import_
                    content = None

                    if len(data.body.import_.score_ids) == 50 and sync == "recent":
                        content = (
                            "It seems like some earlier unsynced scores were pushed out of your recents. "
                            f"If any scores are missing, please run `{ctx.clean_prefix}kamaitachi sync pb` to sync your personal bests. "
                            "Please sync more often when you're having large sessions, since syncing recents lets you keep track "
                            "of playcount and judgements."
                        )

                    embed = (
                        discord.Embed(
                            title="Import finished.",
                            color=tachi_client.ACCENT_COLOR,
                            timestamp=datetime.fromtimestamp(
                                import_doc.time_finished / 1000, UTC
                            ),
                        )
                        .add_field(
                            name="Created sessions",
                            value=str(
                                len(
                                    [
                                        s
                                        for s in import_doc.created_sessions
                                        if s.type == "Created"
                                    ]
                                )
                            ),
                        )
                        .add_field(name="Scores", value=str(len(import_doc.score_ids)))
                    )

                    if len(import_doc.errors) > 0:
                        error_content = "\n".join(
                            [f"- {e.type}: {e.message}" for e in import_doc.errors]
                        )

                        if len(error_content) > 1024:
                            error_content = error_content[:1021] + "..."

                        embed.add_field(
                            name="Errors", value=error_content, inline=False
                        )

                    return await ctx.respond_or_edit(
                        content=content,
                        embed=embed,
                        view=(
                            discord.ui.View(timeout=None)
                            .add_item(
                                discord.ui.Button(
                                    style=discord.ButtonStyle.link,
                                    label="CHUNITHM Profile",
                                    url=f"https://kamai.tachi.ac/u/{import_doc.user_id}/games/chunithm/Single",
                                )
                            )
                            .add_item(
                                discord.ui.Button(
                                    style=discord.ButtonStyle.link,
                                    label="Imports",
                                    url=f"https://kamai.tachi.ac/u/{import_doc.user_id}/imports",
                                )
                            )
                        ),
                    )

    @kamaitachi.command("deorphan")
    @logged_prefix_command
    async def kamaitachi_deorphan(self, ctx: PenguinContext):
        """Forces Tachi to reprocess your orphaned scores.

        This is automatically done daily, but this command allows users to speed that up.
        """

        async with ctx.typing(), self.bot.begin_db_session() as session:
            query = select(Cookie).where(Cookie.discord_id == ctx.author.id)
            cookie = (await session.execute(query)).scalar_one_or_none()

        if cookie is None or cookie.kamaitachi_token is None:
            msg = f"You are not linked with Kamaitachi. DM me with `{'/' if ctx.interaction else config.bot.default_prefix}kamaitachi link` for instructions."
            raise commands.CommandError(msg)

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.kamaitachi(
                cookie.kamaitachi_token
            ) as tachi_client,
        ):
            profile = await tachi_client.get_minimal_profile()
            resp = await tachi_client._client.post("/api/v1/import/orphans")

            if resp.status_code != 200:
                msg = f"Could not send a request to deorphan scores (HTTP status {resp.status_code})"
                raise commands.CommandError(msg)

            data = msgspec.json.decode(
                resp.content, type=KTResponse[ReprocessOrphanSummary]
            )

            if not data.success or data.body is None:
                msg = f"Could not deorphan scores: {data.description}"
                raise commands.CommandError(msg)

        await ctx.respond_or_edit(
            embed=(
                discord.Embed(
                    title=f"Processed {data.body.processed} orphan scores.",
                    color=tachi_client.ACCENT_COLOR,
                    timestamp=datetime.now(UTC),
                )
                .add_field(name="Success", value=str(data.body.success))
                .add_field(name="Failed", value=str(data.body.failed))
                .add_field(name="Removed", value=str(data.body.removed))
            ),
            view=(
                discord.ui.View(timeout=None)
                .add_item(
                    discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label="CHUNITHM Profile",
                        url=f"https://kamai.tachi.ac/u/{profile.username}/games/chunithm/Single",
                    )
                )
                .add_item(
                    discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label="Imports",
                        url=f"https://kamai.tachi.ac/u/{profile.username}/imports",
                    )
                )
            ),
        )


async def setup(bot: "ChuniBot"):
    await bot.add_cog(KamaitachiCog(bot))
