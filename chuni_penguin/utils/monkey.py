import contextlib


def patch_json():
    import discord.utils

    from .json import json_dumps, json_loads

    discord.utils._from_json = json_loads
    discord.utils._to_json = json_dumps


def patch_parse_timestamp():
    with contextlib.suppress(ImportError):
        import ciso8601
        import discord.utils

        discord.utils.parse_time = (
            lambda timestamp: None
            if timestamp is None
            else ciso8601.parse_datetime(timestamp)
        )


def patch_all():
    patch_json()
    patch_parse_timestamp()
