import sys


def get_loop_factory():
    try:
        if sys.platform == "win32":
            import winloop  # pyright: ignore[reportMissingImports]

            return winloop.new_event_loop

        import uvloop  # pyright: ignore[reportMissingImports]
    except ImportError:
        import asyncio

        return asyncio.new_event_loop
    else:
        return uvloop.new_event_loop
