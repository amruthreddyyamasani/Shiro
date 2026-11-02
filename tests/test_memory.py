from __future__ import annotations

import asyncio

import pytest

from shiro.database import Database
from shiro.memory import (
    MemoryManager,
    _parse_candidates,
    _safe_memory_content,
    _keywords,
)


class FakeOllama:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def stream_chat(self, messages):
        self.calls.append(messages)
        yield self.response


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "memory_test.db")
    db.initialize()
    return db


def test_parse_valid_memory_candidates():
    raw = """
    {
        "memories": [
            {
                "category": "preferences",
                "content": "Prefers concise explanations."
            },
            {
                "category": "skills",
                "content": "Learning Python."
            }
        ]
    }
    """

    result = _parse_candidates(raw)

    assert len(result) == 2
    assert result[0]["category"] == "preferences"
    assert result[1]["content"] == "Learning Python."


def test_parse_rejects_invalid_category():
    raw = """
    {
        "memories": [
            {
                "category": "passwords",
                "content": "Some random fact."
            }
        ]
    }
    """

    assert _parse_candidates(raw) == []


def test_parse_rejects_sensitive_content():
    raw = """
    {
        "memories": [
            {
                "category": "general",
                "content": "My password is example123."
            }
        ]
    }
    """

    assert _parse_candidates(raw) == []


def test_parse_rejects_invalid_json():
    assert _parse_candidates("not valid JSON") == []


def test_parse_limits_candidates_to_three():
    raw = """
    {
        "memories": [
            {"category": "general", "content": "Fact one."},
            {"category": "general", "content": "Fact two."},
            {"category": "general", "content": "Fact three."},
            {"category": "general", "content": "Fact four."}
        ]
    }
    """

    assert len(_parse_candidates(raw)) == 3


def test_safe_memory_content_rejects_email():
    assert not _safe_memory_content("Contact me at test@example.com")


def test_safe_memory_content_rejects_long_numbers():
    assert not _safe_memory_content("My number is 123456789012")


def test_keyword_extraction():
    result = _keywords("I am learning Python and building SHIRO")

    assert "python" in result
    assert "shiro" in result
    assert "building" in result
    assert "and" not in result


def test_extract_and_store_saves_valid_memory(database):
    fake = FakeOllama(
        """
        {
            "memories": [
                {
                    "category": "preferences",
                    "content": "Prefers concise explanations."
                }
            ]
        }
        """
    )

    manager = MemoryManager(database, fake)

    saved = asyncio.run(
        manager.extract_and_store("I prefer concise explanations.")
    )

    assert len(saved) == 1
    assert saved[0].content == "Prefers concise explanations."
    assert len(database.list_memories()) == 1


def test_extract_and_store_handles_invalid_model_output(database):
    fake = FakeOllama("This is not JSON")
    manager = MemoryManager(database, fake)

    saved = asyncio.run(
        manager.extract_and_store("I like Python.")
    )

    assert saved == []
    assert database.list_memories() == []


def test_extract_and_store_handles_ollama_failure(database):
    class BrokenOllama:
        async def stream_chat(self, messages):
            raise RuntimeError("Ollama unavailable")
            yield ""

    manager = MemoryManager(database, BrokenOllama())

    saved = asyncio.run(
        manager.extract_and_store("I like Python.")
    )

    assert saved == []
    assert database.list_memories() == []


def test_retrieve_relevant_memories(database):
    database.add_memory("preferences", "Prefers concise explanations.")
    database.add_memory("projects", "Building the SHIRO assistant.")
    database.add_memory("skills", "Learning Python programming.")

    manager = MemoryManager(database, FakeOllama(""))

    results = manager.retrieve("Tell me about Python programming")

    assert len(results) >= 1
    assert any("Python" in item.content for item in results)


def test_build_memory_context_returns_none_when_no_match(database):
    manager = MemoryManager(database, FakeOllama(""))

    assert manager.build_memory_context("unrelated query") is None


def test_build_memory_context_includes_relevant_memory(database):
    database.add_memory("projects", "Building the SHIRO assistant.")

    manager = MemoryManager(database, FakeOllama(""))

    context = manager.build_memory_context("Tell me about SHIRO")

    assert context is not None
    assert "SHIRO assistant" in context
