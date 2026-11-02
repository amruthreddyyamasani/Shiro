/**
 * NDJSON stream consumer for /v1/chat/stream
 */
import { MessageRequest, StreamChatEvent } from './types';

export interface StreamCallbacks {
  onToken: (token: string, conversationId: string) => void;
  onDone: (fullContent: string, conversationId: string) => void;
  onError: (error: { code: string; message: string }, conversationId?: string) => void;
}

export async function streamChat(
  request: MessageRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch('/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/x-ndjson',
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) errorDetail = errorJson.detail;
    } catch {
      // ignore
    }
    callbacks.onError({
      code: `http_${response.status}`,
      message: errorDetail,
    });
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError({
      code: 'stream_unavailable',
      message: 'Response body is not readable.',
    });
    return;
  }

  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      // The last element is either empty (if ended in newline) or partial line
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        try {
          const event: StreamChatEvent = JSON.parse(trimmed);
          if (event.type === 'token') {
            callbacks.onToken(event.content, event.conversation_id);
          } else if (event.type === 'done') {
            callbacks.onDone(event.content, event.conversation_id);
          } else if (event.type === 'error') {
            callbacks.onError(event.error, event.conversation_id);
          }
        } catch (parseErr) {
          console.error('Failed to parse NDJSON line:', trimmed, parseErr);
        }
      }
    }

    // Process any remaining bytes
    if (buffer.trim()) {
      try {
        const event: StreamChatEvent = JSON.parse(buffer.trim());
        if (event.type === 'token') {
          callbacks.onToken(event.content, event.conversation_id);
        } else if (event.type === 'done') {
          callbacks.onDone(event.content, event.conversation_id);
        } else if (event.type === 'error') {
          callbacks.onError(event.error, event.conversation_id);
        }
      } catch (parseErr) {
        console.error('Failed to parse final buffer:', buffer, parseErr);
      }
    }
  } catch (err: unknown) {
    if (signal?.aborted) {
      // Aborted by user
      return;
    }
    callbacks.onError({
      code: 'stream_error',
      message: err instanceof Error ? err.message : String(err),
    });
  }
}
