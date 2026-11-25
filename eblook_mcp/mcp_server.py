# -*- coding: utf-8 -*-

# Copyright (C) 2026 MURAMATSU Atsushi <amura@tomato.sakura.ne.jp>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""MCP server exposing the configured eblook dictionaries as tools.

FastMCP (the standalone `fastmcp` package) is the MCP library used here.
__main__ imports this module only when actually starting the server, so the
--config / --gen-config CLI does not require the MCP dependencies.
"""

from __future__ import annotations

import functools
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fastmcp import FastMCP

from . import eblook
from .common import PathEx
from .config import Config
from .eblook import EBLOOK_MENU

LOGGER = logging.getLogger(__name__)

# Returned to clients by set_dictionary() so that they know how to write
# search words for each method. Based on eblook_mcp/docs.md.
SEARCH_QUERY_GUIDE: dict[str, str] = {
    "general": (
        "A leading '*' or trailing '*' is converted to the endword/word "
        "method when possible, and an exact match to 'exact'. "
        "An empty word is not allowed."
    ),
    "glob": (
        "Substring search. Examples: 'word', 'but*' (prefix), "
        "'*aly' (suffix)."
    ),
    "exactword": "Exact word search: 'word'.",
    "keyword": "Join keywords with '=': 'word=word2'.",
    "multi": (
        "Join search keys with ':' and list candidates for a key with ',': "
        "'key1:key2' where each key may be 'a,b'."
    ),
    "cross": "Require all words, joined with '&': 'word1&word2'.",
    "fulltext": (
        "Space or '&' means AND, '|' means OR, '!' means NOT, and double "
        "quotes make a phrase. Prefix/suffix wildcards: 'euro*', '*sphere'."
    ),
}


@runtime_checkable
class HtmlSession(Protocol):
    """The part of eblook.EBhtml that DictionaryService depends on.

    DictionaryService only uses this interface, so tests can replace the
    real implementation with a fake. Annotating `_open` with this protocol
    makes mypy verify that EBhtml still provides every method used here.
    """

    def __enter__(self) -> "HtmlSession": ...

    def __exit__(self, exc_type: object, exc_value: object,
                 traceback: object) -> None: ...

    def set_book(self, path: Path, appendix: PathEx | None = None,
                 alternate_ini: PathEx | None = None) -> EBLOOK_MENU: ...

    def select_book(self, num_or_tag: int | str,
                    gaiji_map: PathEx | None = None) -> list[str]: ...

    @property
    def supported_method(self) -> list[str]: ...

    def search(self, word: str, method: str = "glob",
               ignore_link: bool = True) -> str: ...

    def close(self) -> None: ...


def log_tool_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Log an exception raised by an MCP tool, then re-raise it.

    FastMCP turns the exception into an error reply for the client, so the
    re-raise keeps the protocol behaviour while the log file records the
    traceback.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception:
            LOGGER.exception("%s failed", fn.__name__)
            raise

    return wrapper


class DictionaryService:
    """State and operations behind the MCP tools.

    EBlook drives a single eblook subprocess, so all operations are
    serialised with a lock. Dictionary selection is session state.
    """

    def __init__(self, config: Config):
        self.config = config
        self._selected: str | None = None
        self._methods: dict[str, list[str]] = {}
        self._lock = threading.RLock()

    # -- dictionary selection ------------------------------------------------

    def _resolve(self, tag: str) -> str:
        """Return the config key for a dictionary tag."""
        if tag not in self.config.dictionaries:
            raise ValueError(f"unknown dictionary tag: {tag!r}")
        return tag

    def list_dictionaries(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {
                    "tag": name,
                    "title": dic.title,
                    "description": dic.description,
                }
                for name, dic in sorted(self.config.dictionaries.items())
            ]

    def set_dictionary(self, tag: str) -> dict[str, Any]:
        with self._lock:
            name = self._resolve(tag)
            methods = self._supported_methods(name)
            self._selected = name
            dic = self.config.dictionaries[name]
            return {
                "tag": name,
                "title": dic.title,
                "description": dic.description,
                "supported_methods": methods,
                "search_query_guide": dict(SEARCH_QUERY_GUIDE),
            }

    # -- searching -----------------------------------------------------------

    def _open(self, name: str) -> HtmlSession:
        dic = self.config.dictionaries[name]
        html = eblook.EBhtml(
            self.config.eblook_cmd, self.config.estcmd_cmd,
            self.config.alternate_ini, self.config.max_hits)
        try:
            html.set_book(dic.path, dic.appendix, dic.alternate_ini)
            methods = html.select_book(dic.subbook, dic.mapfile)
        except Exception:
            html.close()
            raise
        self._methods[name] = methods
        return html

    def _supported_methods(self, name: str) -> list[str]:
        if name in self._methods:
            return list(self._methods[name])
        with self._open(name) as html:
            return list(html.supported_method)

    def _search(self, name: str, word: str, method: str) -> str:
        with self._open(name) as html:
            methods = html.supported_method
            if method not in methods:
                raise ValueError(
                    f"unsupported search method {method!r} for {name!r}; "
                    f"supported: {', '.join(methods)}")
            return html.search(word, method=method)

    def search(self, word: str, method: str = "glob") -> str:
        with self._lock:
            if self._selected is None:
                raise ValueError(
                    "no dictionary selected: call set_dictionary first")
            return self._search(self._selected, word, method)

    def search_multiple(
            self, tags: list[str], word: str, method: str = "glob") -> str:
        with self._lock:
            if not tags:
                raise ValueError("no dictionary tags given")
            names = [self._resolve(tag) for tag in tags]
            return '<hr />\n'.join(
                self._search(name, word, method) for name in names)

    @property
    def selected_tag(self) -> str | None:
        return self._selected


def create_server(config: Config) -> FastMCP:
    """Build a FastMCP server exposing the four dictionary tools."""
    service = DictionaryService(config)
    mcp = FastMCP("eblook-mcp")

    @mcp.tool()
    @log_tool_errors
    def list_dictionaries() -> list[dict[str, str]]:
        """List all configured dictionaries.

        Returns the tag and description of each dictionary. Pass a tag to
        set_dictionary to choose which dictionary to search.
        """
        return service.list_dictionaries()

    @mcp.tool()
    @log_tool_errors
    def set_dictionary(tag: str) -> dict[str, Any]:
        """Select the dictionary used by the search tool.

        Args:
            tag: A tag returned by list_dictionaries.

        Returns:
            The supported search methods and a guide explaining how to
            write search words for each method.
        """
        return service.set_dictionary(tag)

    @mcp.tool()
    @log_tool_errors
    def search(word: str, method: str = "glob") -> str:
        """Search the selected dictionary and return the entries as HTML.

        Args:
            word: Search word. See search_query_guide from set_dictionary.
            method: One of the methods returned by set_dictionary.
        """
        return service.search(word, method)

    @mcp.tool()
    @log_tool_errors
    def search_multiple(
            tags: list[str], word: str, method: str = "glob") -> str:
        """Search several dictionaries and return one combined HTML document.

        Args:
            tags: Tags returned by list_dictionaries.
            word: Search word, applied to every dictionary.
            method: One of the supported search methods.
        """
        return service.search_multiple(tags, word, method)

    return mcp
