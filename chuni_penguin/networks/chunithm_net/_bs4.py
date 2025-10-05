import importlib.util

BS4_FEATURE = "lxml" if importlib.util.find_spec("lxml") else "html.parser"
