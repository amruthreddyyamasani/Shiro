import React, { useRef, useEffect, useState } from 'react';
import { Bot, PanelRight, Sparkles, AlertCircle } from 'lucide-react';
import { useChat } from '../../hooks/useChat';
import { MessageItem } from './MessageItem';
import { Composer } from './Composer';
import { Button } from '../ui/Button';
import { api } from '../../api/client';

interface ChatViewProps {
  activeModel: string;
  isOnline: boolean;
  onToggleContextPanel: () => void;
  isContextPanelOpen: boolean;
  activeConversationId?: string | null;
  onSelectConversation?: (cid: string | null) => void;
  onRefreshConversations?: () => void;
  onStreamingChange?: (isStreaming: boolean) => void;
}

export const ChatView: React.FC<ChatViewProps> = ({
  activeModel,
  isOnline,
  onToggleContextPanel,
  isContextPanelOpen,
  activeConversationId,
  onSelectConversation,
  onRefreshConversations,
  onStreamingChange,
}) => {
  const [personalityMode, setPersonalityMode] = useState<string>('adaptive');

  useEffect(() => {
    api.getSettings().then((s) => setPersonalityMode(s.personality_mode)).catch(() => {});
  }, []);

  const {
    conversationId,
    messages,
    isStreaming,
    error,
    sendMessage,
    stopStreaming,
    startNewConversation,
    loadConversation,
  } = useChat(onRefreshConversations);

  useEffect(() => {
    onStreamingChange?.(isStreaming);
  }, [isStreaming, onStreamingChange]);

  useEffect(() => {
    return () => onStreamingChange?.(false);
  }, [onStreamingChange]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Sync external conversationId selection
  useEffect(() => {
    if (activeConversationId && activeConversationId !== conversationId) {
      loadConversation(activeConversationId);
    } else if (activeConversationId === null && conversationId !== null) {
      startNewConversation();
    }
  }, [activeConversationId, conversationId, loadConversation, startNewConversation]);

  // Notify parent if a new conversation was assigned
  useEffect(() => {
    if (conversationId && conversationId !== activeConversationId) {
      onSelectConversation?.(conversationId);
    }
  }, [conversationId, activeConversationId, onSelectConversation]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const quickPrompts = [
    'What tools are registered on this system?',
    'List files in my approved workspace directory.',
    'Explain how SHIRO executes tasks safely on Windows.',
    'Calculate the square root of 1048576 multiplied by 42.',
  ];

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-background">
      {/* Top Chat Header */}
      <div className="px-4 py-3 border-b border-border bg-sidebar/50 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-semibold text-text-primary uppercase tracking-wider">
              {conversationId ? 'CONVERSATION' : 'NEW CONVERSATION'}
            </span>
            {messages.length > 0 && (
              <span className="text-[10px] font-mono text-text-muted">
                ({messages.length} msgs)
              </span>
            )}
          </div>

          <div className="hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface border border-border text-[11px] font-mono text-text-secondary">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan" />
            <span>{activeModel}</span>
          </div>

          <div className="hidden md:flex items-center gap-1 px-2 py-0.5 rounded bg-surface border border-border text-[11px] font-mono text-text-muted">
            <Sparkles className="w-3 h-3 text-accent-cyan" />
            <span className="capitalize">{personalityMode}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <Button size="sm" variant="ghost" onClick={startNewConversation}>
              Clear
            </Button>
          )}

          <button
            onClick={onToggleContextPanel}
            className={`p-1.5 rounded border transition-colors ${
              isContextPanelOpen
                ? 'bg-accent-cyan/10 border-accent-cyan/40 text-accent-cyan'
                : 'border-border text-text-muted hover:text-text-primary hover:bg-surface-raised'
            }`}
            title="Toggle Context & Tasks Panel (Ctrl+B)"
          >
            <PanelRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Error alert if any */}
      {error && (
        <div className="p-3 mx-4 mt-3 rounded bg-red-950/30 border border-red-800 text-red-300 text-xs flex items-center gap-2 shrink-0">
          <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto px-4 md:px-8 py-4 space-y-2">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-6 max-w-lg mx-auto">
            <div className="w-12 h-12 rounded-xl bg-surface-raised border border-border flex items-center justify-center text-accent-cyan shadow-sm">
              <Bot className="w-6 h-6" />
            </div>

            <div className="space-y-2">
              <h2 className="text-base font-bold font-mono text-text-primary tracking-wide">
                SHIRO LOCAL INTELLIGENCE
              </h2>
              <p className="text-xs text-text-secondary leading-relaxed">
                Running locally on Windows via Ollama. Responses are streamed directly with zero cloud
                leakage. Approved memory context is automatically retrieved.
              </p>
            </div>

            <div className="w-full space-y-2 pt-2">
              <span className="text-[11px] font-mono text-text-muted uppercase tracking-wider block text-left">
                Suggested Prompts
              </span>
              <div className="grid grid-cols-1 gap-2 text-left">
                {quickPrompts.map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(prompt)}
                    className="p-2.5 rounded-lg bg-surface border border-border hover:border-accent-cyan/50 text-xs text-text-secondary hover:text-text-primary transition-colors flex items-center justify-between group"
                  >
                    <span>{prompt}</span>
                    <Sparkles className="w-3.5 h-3.5 text-text-muted group-hover:text-accent-cyan shrink-0 ml-2" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg) => <MessageItem key={msg.id} message={msg} />)
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Composer */}
      <Composer
        onSend={sendMessage}
        onStop={stopStreaming}
        isStreaming={isStreaming}
        disabled={!isOnline}
      />
    </div>
  );
};
