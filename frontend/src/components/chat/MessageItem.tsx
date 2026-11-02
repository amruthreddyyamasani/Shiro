import React, { useState } from 'react';
import { Copy, Check, User, Bot } from 'lucide-react';
import { ChatMessage } from '../../hooks/useChat';
import { formatDate } from '../../lib/utils';

interface MessageItemProps {
  message: ChatMessage;
}

export const MessageItem: React.FC<MessageItemProps> = ({ message }) => {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Basic formatted rendering (lines, code blocks)
  const renderFormattedContent = (text: string) => {
    const parts = text.split(/(```[\s\S]*?```)/g);

    return parts.map((part, index) => {
      if (part.startsWith('```') && part.endsWith('```')) {
        const lines = part.slice(3, -3).trim().split('\n');
        const language = lines[0].match(/^[a-zA-Z0-9_-]+$/) ? lines[0] : '';
        const code = language ? lines.slice(1).join('\n') : lines.join('\n');

        return (
          <div
            key={index}
            className="my-3 rounded-lg overflow-hidden border border-border bg-[#05070a] text-xs font-mono"
          >
            {language && (
              <div className="px-3 py-1 bg-surface-raised border-b border-border text-[11px] text-text-muted flex items-center justify-between">
                <span>{language}</span>
              </div>
            )}
            <pre className="p-3 overflow-x-auto text-[#53d9f2] font-mono leading-relaxed whitespace-pre">
              <code>{code}</code>
            </pre>
          </div>
        );
      }

      // Normal text paragraphs
      return (
        <span key={index} className="whitespace-pre-wrap leading-relaxed">
          {part}
        </span>
      );
    });
  };

  return (
    <div className={`flex gap-3 py-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-md bg-accent-cyan/10 border border-accent-cyan/30 flex items-center justify-center text-accent-cyan shrink-0 mt-0.5">
          <Bot className="w-4 h-4" />
        </div>
      )}

      <div
        className={`max-w-[85%] rounded-lg p-3.5 space-y-1.5 ${
          isUser
            ? 'bg-surface-raised border border-border text-text-primary'
            : 'bg-surface border border-border text-text-primary'
        }`}
      >
        <div className="flex items-center justify-between gap-4 text-[11px] text-text-muted font-mono pb-1 border-b border-border-subtle">
          <span className="font-semibold text-text-secondary">
            {isUser ? 'YOU' : 'SHIRO'}
          </span>
          <div className="flex items-center gap-2">
            <span>{formatDate(message.created_at)}</span>
            {!isUser && message.content && (
              <button
                onClick={handleCopy}
                className="p-1 rounded hover:bg-surface-elevated text-text-muted hover:text-text-primary transition-colors"
                title="Copy text"
              >
                {copied ? (
                  <Check className="w-3 h-3 text-emerald-400" />
                ) : (
                  <Copy className="w-3 h-3" />
                )}
              </button>
            )}
          </div>
        </div>

        <div className="text-sm">
          {renderFormattedContent(message.content)}
          {message.isStreaming && (
            <span className="inline-block w-2 h-4 ml-1 bg-accent-cyan animate-pulse align-middle" />
          )}
        </div>
      </div>

      {isUser && (
        <div className="w-7 h-7 rounded-md bg-surface-raised border border-border flex items-center justify-center text-text-secondary shrink-0 mt-0.5">
          <User className="w-4 h-4" />
        </div>
      )}
    </div>
  );
};
