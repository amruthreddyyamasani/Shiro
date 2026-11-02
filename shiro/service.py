
"""Application orchestration for conversations, memory and streamed output."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from .config import Settings
from .database import Database
from .memory import MemoryManager
from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)


PERSONALITY_PROMPTS = {
    "adaptive": (
        "You are SHIRO, a friendly companion and professional local assistant. "
        "Adapt your explanation depth and tone to the user's request. "
        "Be concise for simple questions and methodical for complex work. "
        "Do not claim to have taken an action unless the system confirms it."
    ),
    "friendly": (
        "You are SHIRO, a warm and encouraging local assistant. "
        "Explain things clearly and respectfully, without being overbearing."
    ),
    "professional": (
        "You are SHIRO, a precise and professional local assistant. "
        "Use clear structure, state assumptions, and distinguish plans from completed actions."
    ),
}


class ConversationNotFound(LookupError):
    """The requested conversation does not exist."""


@dataclass(frozen=True)
class PreparedChat:
    conversation_id: str
    user_message: str
    messages: list[dict[str, str]]


class ShiroService:
    """Coordinate persistence, memory and local model calls."""

    def __init__(self, settings: Settings, database: Database, ollama: OllamaClient):
        self.settings = settings
        self.database = database
        self.ollama = ollama
        self.memory = MemoryManager(database, ollama)

    def create_conversation(self, title: str | None = None):
        return self.database.create_conversation(title)

    def list_conversations(self, limit: int = 100):
        return self.database.list_conversations(limit=limit)

    def get_conversation(self, conversation_id: str):
        return self.database.get_conversation(conversation_id)

    def delete_conversation(self, conversation_id: str):
        return self.database.delete_conversation(conversation_id)

    def list_messages(self, conversation_id: str):
        if self.database.get_conversation(conversation_id) is None:
            raise ConversationNotFound(conversation_id)

        return self.database.list_messages(
            conversation_id,
            limit=self.settings.max_history_messages,
        )

    def prepare_chat(
        self,
        conversation_id: str | None,
        content: str,
    ) -> PreparedChat:
        conversation = (
            self.database.get_conversation(conversation_id)
            if conversation_id
            else self.database.create_conversation()
        )

        if conversation is None:
            raise ConversationNotFound(conversation_id or "")

        self.database.append_message(conversation.id, "user", content)

        history = self.database.list_messages(
            conversation.id,
            limit=self.settings.max_history_messages,
        )

        messages = [
            {"role": message.role, "content": message.content}
            for message in history
        ]

        messages.insert(
            0,
            {
                "role": "system",
                "content": PERSONALITY_PROMPTS[self.settings.personality_mode],
            },
        )

        # Relevant long-term memory is added separately from conversation history.
        memory_context = self.memory.build_memory_context(content)

        if memory_context:
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": memory_context,
                },
            )

        return PreparedChat(
            conversation_id=conversation.id,
            user_message=content,
            messages=messages,
        )

    async def stream_prepared_chat(
        self,
        prepared: PreparedChat,
    ) -> AsyncIterator[dict[str, object]]:
        parts: list[str] = []

        try:
            async for token in self.ollama.stream_chat(prepared.messages):
                parts.append(token)

                yield {
                    "type": "token",
                    "conversation_id": prepared.conversation_id,
                    "content": token,
                }

            assistant_content = "".join(parts)

            if assistant_content:
                self.database.append_message(
                    prepared.conversation_id,
                    "assistant",
                    assistant_content,
                )

            # Send the completed response before doing the separate memory pass.
            yield {
                "type": "done",
                "conversation_id": prepared.conversation_id,
                "content": assistant_content,
            }

            # This runs after the done event has been yielded. Memory failures
            # must never turn a successful chat response into a failed response.
            try:
                await self.memory.extract_and_store(prepared.user_message)
            except Exception:
                logger.exception(
                    "Unexpected memory processing failure for conversation %s",
                    prepared.conversation_id,
                )

        except Exception as exc:
            logger.exception(
                "Chat stream failed for conversation %s",
                prepared.conversation_id,
            )

            yield {
                "type": "error",
                "conversation_id": prepared.conversation_id,
                "error": {
                    "code": "ollama_error",
                    "message": str(exc),
                },
            }
