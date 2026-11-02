import { useState, useRef, useCallback, useEffect } from 'react';
import { api } from '../api/client';
import { streamChat } from '../api/stream';
import { MessageResponse } from '../api/types';

export interface ChatMessage {
  id: string | number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  isStreaming?: boolean;
}

export function useChat(onConversationCreatedOrUpdated?: (cid: string) => void) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Load message history if a conversationId is set
  const loadConversation = useCallback(async (cid: string) => {
    try {
      setError(null);
      const history = await api.getMessages(cid);
      setConversationId(cid);
      setMessages(
        history.map((m: MessageResponse) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          created_at: m.created_at,
        }))
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const startNewConversation = useCallback(() => {
    if (isStreaming) {
      abortControllerRef.current?.abort();
      setIsStreaming(false);
    }
    setConversationId(null);
    setMessages([]);
    setError(null);
  }, [isStreaming]);

  const sendMessage = useCallback(
    async (content: string) => {
      const text = content.trim();
      if (!text || isStreaming) return;

      setError(null);

      const userMsgId = `user-${Date.now()}`;
      const assistantMsgId = `asst-${Date.now()}`;
      const now = new Date().toISOString();

      // Optimistically append user message & empty assistant placeholder
      setMessages((prev) => [
        ...prev,
        { id: userMsgId, role: 'user', content: text, created_at: now },
        { id: assistantMsgId, role: 'assistant', content: '', created_at: now, isStreaming: true },
      ]);

      setIsStreaming(true);
      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        await streamChat(
          {
            content: text,
            conversation_id: conversationId,
          },
          {
            onToken: (token, returnedCid) => {
              if (!conversationId && returnedCid) {
                setConversationId(returnedCid);
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, content: msg.content + token, isStreaming: true }
                    : msg
                )
              );
            },
            onDone: (fullContent, returnedCid) => {
              if (returnedCid) {
                setConversationId(returnedCid);
                onConversationCreatedOrUpdated?.(returnedCid);
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, content: fullContent, isStreaming: false }
                    : msg
                )
              );
              setIsStreaming(false);
            },
            onError: (err, returnedCid) => {
              if (!conversationId && returnedCid) {
                setConversationId(returnedCid);
              }
              setError(err.message);
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? {
                        ...msg,
                        content: msg.content || `[Error: ${err.message}]`,
                        isStreaming: false,
                      }
                    : msg
                )
              );
              setIsStreaming(false);
            },
          },
          controller.signal
        );
      } catch (err: unknown) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : String(err));
          setIsStreaming(false);
        }
      }
    },
    [conversationId, isStreaming]
  );

  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
      setMessages((prev) =>
        prev.map((msg) => (msg.isStreaming ? { ...msg, isStreaming: false } : msg))
      );
    }
  }, []);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return {
    conversationId,
    messages,
    isStreaming,
    error,
    sendMessage,
    stopStreaming,
    startNewConversation,
    loadConversation,
  };
}
