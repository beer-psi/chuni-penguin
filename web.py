import string
import sys
from html import escape
from typing import TYPE_CHECKING, Optional

import aiohttp
import discord
from aiohttp import ClientSession, web
from discord.utils import oauth_url
from sqlalchemy import select

from database.models import Cookie
from utils import json_loads

if TYPE_CHECKING:
    from bot import ChuniBot


__all__ = ("init_app",)


COOKIE_CHARACTERS = string.ascii_lowercase + string.digits


router = web.RouteTableDef()


@router.get("/")
async def index(request: web.Request) -> web.Response:
    return web.Response(
        body="https://github.com/beer-psi/chuni-penguin",
        content_type="text/plain",
    )


@router.get("/kamaitachi/oauth")
async def kamaitachi_oauth(request: web.Request) -> web.Response:
    if (
        (kamaitachi_client_id := request.config_dict["kamaitachi_client_id"]) is None
        or (kamaitachi_client_secret := request.config_dict["kamaitachi_client_secret"])
        is None
        or (base_url := request.config_dict["base_url"]) is None
    ):
        raise web.HTTPInternalServerError(
            reason="Some options are not configured. Yell at the bot owner."
        )

    session: ClientSession = request.config_dict["session"] or ClientSession()
    params = request.query
    if "code" not in params or "context" not in params:
        raise web.HTTPBadRequest(reason="Missing parameters")

    try:
        discord_id = int(params["context"])
    except ValueError:
        raise web.HTTPBadRequest(reason="Invalid context parameter") from None

    bot: ChuniBot = request.config_dict["bot"]
    async with bot.begin_db_session() as db_session:
        stmt = select(Cookie).where(Cookie.discord_id == discord_id)
        cookie = (await db_session.execute(stmt)).scalar_one_or_none()

    async with session.post(
        "https://kamai.tachi.ac/api/v1/oauth/token",
        json={
            "code": params["code"],
            "client_id": kamaitachi_client_id,
            "client_secret": kamaitachi_client_secret,
            "grant_type": "authorization_code",
            "redirect_uri": f"{base_url}/kamaitachi/oauth",
        },
    ) as resp:
        data = await resp.json(loads=json_loads)

    if not data["success"]:
        raise web.HTTPUnauthorized(
            reason=f"Failed to authenticate: {data['description']}"
        )

    token = data["body"]["token"]

    async with session.get(
        "https://kamai.tachi.ac/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    ) as resp:
        whoami_data = await resp.json(loads=json_loads)

    if not whoami_data["success"]:
        raise web.HTTPInternalServerError

    async with bot.begin_db_session() as db_session, db_session.begin():
        if cookie is None:
            cookie = Cookie(discord_id=discord_id, cookie="", kamaitachi_token=token)
            db_session.add(cookie)
        else:
            cookie.kamaitachi_token = token
            await db_session.merge(cookie)

    return web.Response(
        text="Your accounts are now linked! You can close this page and use the bot now.",
        content_type="text/plain",
    )


@router.get("/invite")
async def invite(request: web.Request) -> web.Response:
    bot: ChuniBot = request.config_dict["bot"]
    if bot.user is None:
        raise web.HTTPInternalServerError(reason="Bot is not ready yet.")

    permissions = discord.Permissions(
        read_messages=True,
        send_messages=True,
        send_messages_in_threads=True,
        manage_messages=True,
        read_message_history=True,
    )
    url = oauth_url(bot.user.id, permissions=permissions)

    raise web.HTTPFound(url)


@router.post("/login")
async def login(request: web.Request) -> web.Response:
    bot: ChuniBot = request.config_dict["bot"]

    params = {}
    content_type = request.headers.get("Content-Type")
    if content_type == "application/json":
        params = await request.json(loads=json_loads)
    elif content_type in ["application/x-www-form-urlencoded", "multipart/form-data"]:
        params = await request.post()
    else:
        raise web.HTTPBadRequest(reason="Invalid Content-Type")

    if "otp" not in params or "clal" not in params:
        raise web.HTTPBadRequest(reason="Missing parameters")

    otp = params["otp"]
    clal = params["clal"]
    if not isinstance(otp, str) or not isinstance(clal, str):
        raise web.HTTPBadRequest(reason="Invalid parameters")

    if clal.startswith("clal="):
        clal = clal[5:]

    if len(clal) != 64 or any(c not in COOKIE_CHARACTERS for c in clal):
        raise web.HTTPBadRequest(reason="Invalid cookie provided")

    if not otp.isdigit() and len(otp) != 6:
        raise web.HTTPBadRequest(reason="Invalid passcode provided")

    bot.dispatch(f"chunithm_login_{otp}", clal)

    goatcounter: str = request.config_dict["goatcounter"]
    goatcounter_tag = (
        f'<script data-goatcounter="{goatcounter}" async src="//gc.zgo.at/count.js"></script>'
        if goatcounter
        else ""
    )
    return web.Response(
        text=f"""
<!DOCTYPE html>
<html lang="en">
    <head>
        <title>chuni penguin login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta charset="utf-8">
        {goatcounter_tag}
    </head>
    <body>
        <h1>Success!</h1>
        <p>Check the bot's DMs to see if the account has been successfully linked.</p>
        
        <div>
            <p>mimi xd bot users can use this command to log in:</p>
            <code>m>login clal={escape(clal)}</code>
        </div>

        <img alt="Chuni Penguin sleeping" src="https://chunithm-net-eng.com/mobile/images/pen_sleep_apng.png">
    </body>
</html>
""",
        content_type="text/html",
    )


async def on_response_prepare(_: web.Request, response: web.StreamResponse):
    response.headers.add("x-content-type-options", "nosniff")
    if response.headers.get("server"):
        del response.headers["server"]


async def on_shutdown(app: web.Application):
    await app["session"].close()


def init_app(
    bot: "ChuniBot",
    *,
    base_url: Optional[str] = None,
    goatcounter: Optional[str] = None,
    kamaitachi_client_id: Optional[str] = None,
    kamaitachi_client_secret: Optional[str] = None,
) -> web.Application:
    app = web.Application()
    app.on_response_prepare.append(on_response_prepare)
    app.on_shutdown.append(on_shutdown)

    app.add_routes(router)

    session = ClientSession()
    session.headers.add(
        "User-Agent",
        f"chuni-penguin (+https://github.com/beer-psi/chuni-penguin) Python/{sys.version_info[0]}.{sys.version_info[1]} aiohttp/{aiohttp.__version__}",
    )

    app["bot"] = bot
    app["session"] = session

    app["base_url"] = base_url
    app["goatcounter"] = goatcounter
    app["kamaitachi_client_id"] = kamaitachi_client_id
    app["kamaitachi_client_secret"] = kamaitachi_client_secret

    return app
