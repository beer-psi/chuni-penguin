import asyncio
import importlib.util
import sys


def get_event_loop():
    event_loop_impl = asyncio
    loop_factory = asyncio.new_event_loop

    if sys.platform == "win32" and importlib.util.find_spec("winloop"):
        import winloop  # type: ignore[reportMissingImports]

        loop_factory = winloop.new_event_loop
        event_loop_impl = winloop
    elif sys.platform != "win32" and importlib.util.find_spec("uvloop"):
        import uvloop  # type: ignore[reportMissingImports]

        loop_factory = uvloop.new_event_loop
        event_loop_impl = uvloop

    return event_loop_impl, loop_factory
