import discord

from chuni_penguin.database import Denylist


class BannedEmbed(discord.Embed):
    def __init__(
        self,
        *,
        client: discord.Client,
        entry: Denylist,
        server_name: str | None,
        support_server_invite: str | None,
    ):
        super().__init__(color=discord.Color.red(), title="Banned")

        bot_mention = client.user.mention if client.user is not None else "the bot"

        if server_name is not None:
            self.description = (
                f"The server {server_name} has been banned from using {bot_mention}."
            )
        else:
            self.description = f"You have been banned from using {bot_mention}."

        if support_server_invite is not None:
            self.description += f"\nIf you have any questions regarding your ban, or would like to appeal, please join the [support server]({support_server_invite})."

        if entry.reason is not None:
            self.add_field(name="Reason", value=entry.reason, inline=False)
