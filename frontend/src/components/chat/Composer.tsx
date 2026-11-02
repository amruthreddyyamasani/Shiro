import React, { useState, useRef, useEffect } from 'react';
import { Send, Square, ShieldCheck } from 'lucide-react';
import { Button } from '../ui/Button';

interface ComposerProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export const Composer: React.FC<ComposerProps> = ({
  onSend,
  onStop,
  isStreaming,
  disabled = false,
}) => {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (!input.trim() || isStreaming || disabled) return;
    onSend(input);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  return (
    <div className="p-4 bg-background border-t border-border">
      <div className="relative rounded-lg border border-border bg-surface-input focus-within:border-accent-cyan/60 transition-colors shadow-sm">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            disabled
              ? 'Local inference offline. Start Ollama on 127.0.0.1:11434...'
              : 'Ask SHIRO anything or instruct a task (Enter to send, Shift+Enter for newline)...'
          }
          disabled={disabled}
          rows={1}
          className="w-full bg-transparent px-3.5 pt-3 pb-10 text-sm text-text-primary placeholder:text-text-muted focus:outline-none resize-none font-sans"
        />

        <div className="absolute bottom-2 left-3 right-2 flex items-center justify-between text-xs text-text-muted font-mono select-none">
          <div className="flex items-center gap-1.5 text-[11px]">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Local Ollama &bull; No Cloud Telemetry</span>
          </div>

          <div className="flex items-center gap-2">
            {isStreaming ? (
              <Button
                size="sm"
                variant="danger"
                onClick={onStop}
                className="h-7 px-2.5 text-xs font-mono"
              >
                <Square className="w-3 h-3 fill-current mr-1" />
                <span>Stop</span>
              </Button>
            ) : (
              <Button
                size="sm"
                variant="primary"
                onClick={handleSend}
                disabled={!input.trim() || disabled}
                className="h-7 px-3 text-xs font-mono"
              >
                <span>Send</span>
                <Send className="w-3 h-3 ml-1" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
