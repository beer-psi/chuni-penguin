# pyright: reportMissingImports=false
from bs4 import BeautifulSoup
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.pages import Page

try:
    import lxml  # pyright: ignore[reportUnusedImport]  # noqa: F401
except ImportError:
    _BS4_FEATURE = "html.parser"
else:
    _BS4_FEATURE = "lxml"


def _is_external_url(href: str, config: MkDocsConfig):
    if href.startswith(("http", "https")):
        return not href.startswith(
            ("http://127.0.0.1", "https://127.0.0.1", config["site_url"])
        )

    return False


def on_post_page(output: str, page: Page, config: MkDocsConfig):
    if not output:
        return output

    soup = BeautifulSoup(output, _BS4_FEATURE)

    for anchor in soup.find_all("a", {"href": True}):
        href = anchor["href"]

        if not href or not _is_external_url(href, config):
            continue

        anchor["target"] = "_blank"
        anchor["rel"] = "noopener noreferrer"

        try:
            anchor["class"].append("external-link")
        except KeyError:
            anchor["class"] = ["external-link"]

    return str(soup)
