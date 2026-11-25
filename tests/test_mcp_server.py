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

"""Tests for the MCP dictionary service.

The MCP SDK itself is not needed for the service tests: create_server's
import is stubbed in the tool-registration test.
"""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from _helpers import DICT_ROOT, requires_dictionary, requires_eblook
from eblook_mcp import config, eblook, mcp_server
from eblook_mcp.common import PathEx
from eblook_mcp.eblook import EBLOOK_MENU
from eblook_mcp.mcp_server import (
    DictionaryService, HtmlSession, SEARCH_QUERY_GUIDE)


def make_config() -> config.Config:
    return config.Config(
        dictionaries={
            "b1:t1": config.Dictionary(
                name="b1:t1", path=Path("/dicts/one"), subbook="t1",
                title="One", description="first"),
            "b2:t2": config.Dictionary(
                name="b2:t2", path=Path("/dicts/two"), subbook="t2",
                title="Two", description="second"),
        },
        max_hits=7)


class FakeHtml:
    """Stand-in for EBhtml that records the calls DictionaryService makes.

    The signatures mirror mcp_server.HtmlSession, so a change to the
    interface used by DictionaryService shows up as a test failure.
    """

    supported = ["glob", "exactword"]

    def __init__(self, *args: object) -> None:
        self.init_args = args
        self.set_book_args: tuple[object, ...] | None = None
        self.select_book_args: tuple[object, ...] | None = None
        self.search_calls: list[tuple[str, str]] = []
        self.closed = False

    def __enter__(self) -> "FakeHtml":
        return self

    def __exit__(self, exc_type: object, exc_value: object,
                 traceback: object) -> None:
        self.close()

    def set_book(self, path: Path, appendix: PathEx | None = None,
                 alternate_ini: PathEx | None = None) -> EBLOOK_MENU:
        self.set_book_args = (path, appendix, alternate_ini)
        return []

    def select_book(self, num_or_tag: int | str,
                    gaiji_map: PathEx | None = None) -> list[str]:
        self.select_book_args = (num_or_tag, gaiji_map)
        return list(self.supported)

    @property
    def supported_method(self) -> list[str]:
        return list(self.supported)

    def search(self, word: str, method: str = "glob",
               ignore_link: bool = True) -> str:
        self.search_calls.append((word, method))
        assert self.select_book_args is not None
        return f"<h2>{self.select_book_args[0]}</h2>{word}:{method}"

    def close(self) -> None:
        self.closed = True


def test_fake_html_satisfies_session_protocol() -> None:
    assert isinstance(FakeHtml(), HtmlSession)


Service = tuple[DictionaryService, list[FakeHtml]]


def make_factory(instances: list[FakeHtml]) -> Callable[..., FakeHtml]:
    def factory(*args: object) -> FakeHtml:
        instance = FakeHtml(*args)
        instances.append(instance)
        return instance
    return factory


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> Service:
    instances: list[FakeHtml] = []
    monkeypatch.setattr(eblook, "EBhtml", make_factory(instances))
    return DictionaryService(make_config()), instances


# ---------------------------------------------------------------------------
# tool 1: list_dictionaries
# ---------------------------------------------------------------------------

def test_list_dictionaries(service: Service) -> None:
    svc, instances = service
    result = svc.list_dictionaries()
    assert [entry["tag"] for entry in result] == ["b1:t1", "b2:t2"]
    assert result[0]["description"] == "first"
    assert result[0]["title"] == "One"
    assert "subbook" not in result[0]
    assert not instances  # must not spawn eblook


# ---------------------------------------------------------------------------
# tool 2: set_dictionary
# ---------------------------------------------------------------------------

def test_set_dictionary_returns_methods_and_guide(service: Service) -> None:
    svc, instances = service
    info = svc.set_dictionary("b1:t1")

    assert info["tag"] == "b1:t1"
    assert "subbook" not in info
    assert info["description"] == "first"
    assert info["supported_methods"] == ["glob", "exactword"]
    assert info["search_query_guide"] == SEARCH_QUERY_GUIDE
    assert svc.selected_tag == "b1:t1"
    assert instances[0].init_args == ("eblook", "estcmd", None, 7)
    assert instances[0].set_book_args == (Path("/dicts/one"), None, None)
    select_book_args = instances[0].select_book_args
    assert select_book_args is not None
    assert select_book_args[0] == "t1"


def test_set_dictionary_rejects_subbook_name(service: Service) -> None:
    svc, _ = service
    with pytest.raises(ValueError, match="unknown dictionary tag"):
        svc.set_dictionary("t2")


def test_set_dictionary_unknown_tag(service: Service) -> None:
    svc, _ = service
    with pytest.raises(ValueError, match="unknown dictionary tag"):
        svc.set_dictionary("missing")


def test_set_dictionary_reuses_cached_methods(service: Service) -> None:
    svc, instances = service
    svc.set_dictionary("b1:t1")
    svc.set_dictionary("b1:t1")
    # the second call must not spawn another eblook process
    assert len(instances) == 1


def test_set_dictionary_closes_html_when_open_fails(
        monkeypatch: pytest.MonkeyPatch) -> None:
    instances: list[FakeHtml] = []

    class FailingHtml(FakeHtml):
        def set_book(self, path: Path, appendix: PathEx | None = None,
                     alternate_ini: PathEx | None = None) -> EBLOOK_MENU:
            super().set_book(path, appendix, alternate_ini)
            raise RuntimeError("book failed")

    def factory(*args: object) -> FakeHtml:
        instance = FailingHtml(*args)
        instances.append(instance)
        return instance

    monkeypatch.setattr(eblook, "EBhtml", factory)
    svc = DictionaryService(make_config())
    with pytest.raises(RuntimeError, match="book failed"):
        svc.set_dictionary("b1:t1")
    assert instances[0].closed


# ---------------------------------------------------------------------------
# tool 3: search
# ---------------------------------------------------------------------------

def test_search_requires_selection(service: Service) -> None:
    svc, _ = service
    with pytest.raises(ValueError, match="no dictionary selected"):
        svc.search("word")


def test_search_uses_selected_dictionary(service: Service) -> None:
    svc, instances = service
    svc.set_dictionary("b1:t1")
    html = svc.search("犬", "glob")

    assert html == "<h2>t1</h2>犬:glob"
    assert instances[-1].search_calls == [("犬", "glob")]
    assert instances[-1].closed


def test_search_rejects_unsupported_method(service: Service) -> None:
    svc, _ = service
    svc.set_dictionary("b1:t1")
    with pytest.raises(ValueError, match="unsupported search method"):
        svc.search("word", "fulltext")


# ---------------------------------------------------------------------------
# tool 4: search_multiple
# ---------------------------------------------------------------------------

def test_search_multiple_combines_html(service: Service) -> None:
    svc, instances = service
    svc.set_dictionary("b1:t1")

    html = svc.search_multiple(["b1:t1", "b2:t2"], "word", "glob")

    assert "<h2>t1</h2>word:glob" in html
    assert "<h2>t2</h2>word:glob" in html
    assert "<hr />" in html
    assert svc.selected_tag == "b1:t1"  # the selection is unchanged
    # set_dictionary + one fresh EBhtml per searched dictionary
    assert len(instances) == 3


def test_search_multiple_empty(service: Service) -> None:
    svc, _ = service
    with pytest.raises(ValueError, match="no dictionary tags"):
        svc.search_multiple([], "word")


def test_search_multiple_unknown_tag(service: Service) -> None:
    svc, _ = service
    with pytest.raises(ValueError, match="unknown dictionary tag"):
        svc.search_multiple(["missing"], "word")


# ---------------------------------------------------------------------------
# tool registration
# ---------------------------------------------------------------------------

def test_create_server_registers_four_tools(
        monkeypatch: pytest.MonkeyPatch) -> None:
    registered: list[str] = []

    class FakeFastMCP:
        def __init__(self, name: str) -> None:
            self.name = name

        def tool(self) -> Callable[[Any], Any]:
            def decorator(fn: Any) -> Any:
                registered.append(fn.__name__)
                return fn
            return decorator

    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)

    server = mcp_server.create_server(make_config())

    assert server.name == "eblook-mcp"
    assert registered == [
        "list_dictionaries", "set_dictionary", "search", "search_multiple"]


# ---------------------------------------------------------------------------
# real dictionaries
# ---------------------------------------------------------------------------

@pytest.mark.integration
@requires_eblook
@requires_dictionary("koujien")
def test_service_with_real_dictionary(tmp_path: Path) -> None:
    (tmp_path / "koujien").symlink_to(DICT_ROOT / "koujien")
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(config.generate_config(tmp_path), encoding="utf-8")

    svc = DictionaryService(config.load_config(cfg_path))
    dictionaries = svc.list_dictionaries()
    assert dictionaries

    name = next(
        tag for tag, dic in svc.config.dictionaries.items()
        if dic.subbook == "kojien")
    assert name in [entry["tag"] for entry in dictionaries]
    info = svc.set_dictionary(name)
    assert "glob" in info["supported_methods"]
    assert svc.search("楽器").startswith("<h2>")
    assert "楽器" in svc.search_multiple([name], "楽器")


@pytest.mark.integration
@requires_eblook
@requires_dictionary("koujien")
def test_tools_over_stdio(tmp_path: Path) -> None:
    """End-to-end check with the real MCP SDK and a stdio subprocess."""
    pytest.importorskip("mcp")
    import asyncio

    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
    from mcp.types import CallToolResult, TextContent

    root = Path(__file__).resolve().parent.parent
    (tmp_path / "koujien").symlink_to(DICT_ROOT / "koujien")
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(config.generate_config(tmp_path), encoding="utf-8")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "eblook_mcp", "--config", str(cfg_path)],
        cwd=str(root))

    async def run() -> None:
        def unwrap(result: CallToolResult) -> Any:
            data = result.structured_content
            if isinstance(data, dict) and set(data) == {"result"}:
                return data["result"]
            return data

        def text_of(result: CallToolResult) -> str:
            return "".join(
                block.text for block in result.content
                if isinstance(block, TextContent))

        async with Client(params) as client:
            tools = await client.list_tools()
            names = [tool.name for tool in tools.tools]
            assert names == [
                "list_dictionaries", "set_dictionary", "search",
                "search_multiple"]

            listed = await client.call_tool("list_dictionaries", {})
            tags = [entry["tag"] for entry in unwrap(listed)]
            assert tags
            # the result must be directly usable as a set_dictionary tag
            name = tags[0]

            selected = await client.call_tool(
                "set_dictionary", {"tag": name})
            info = unwrap(selected)
            assert "glob" in info["supported_methods"]
            assert "search_query_guide" in info

            found = await client.call_tool(
                "search", {"word": "楽器", "method": "glob"})
            assert "楽器" in text_of(found)

            combined = await client.call_tool(
                "search_multiple",
                {"tags": [name], "word": "楽器", "method": "glob"})
            assert "楽器" in text_of(combined)

    asyncio.run(run())
