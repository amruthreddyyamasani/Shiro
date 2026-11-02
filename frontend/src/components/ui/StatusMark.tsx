import React from 'react';
import { cn } from '../../lib/utils';

export type StatusType =
  | 'ok'
  | 'online'
  | 'succeeded'
  | 'running'
  | 'streaming'
  | 'waiting_approval'
  | 'planned'
  | 'paused'
  | 'failed'
  | 'error'
  | 'offline';

interface StatusMarkProps {
  status: StatusType | string;
  label?: string;
  pulse?: boolean;
  className?: string;
}

export const StatusMark: React.FC<StatusMarkProps> = ({
  status,
  label,
  pulse = false,
  className,
}) => {
  const getColors = (s: string) => {
    switch (s.toLowerCase()) {
      case 'ok':
      case 'online':
      case 'succeeded':
        return {
          dot: 'bg-emerald-400',
          bg: 'bg-emerald-950/40 border-emerald-800/40 text-emerald-300',
        };
      case 'running':
      case 'streaming':
        return {
          dot: 'bg-accent-cyan animate-pulse',
          bg: 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan',
        };
      case 'waiting_approval':
      case 'approval_required':
      case 'pending':
        return {
          dot: 'bg-amber-400',
          bg: 'bg-amber-950/40 border-amber-800/40 text-amber-300',
        };
      case 'failed':
      case 'error':
      case 'offline':
        return {
          dot: 'bg-rose-400',
          bg: 'bg-rose-950/40 border-rose-800/40 text-rose-300',
        };
      case 'paused':
      case 'planned':
      default:
        return {
          dot: 'bg-slate-400',
          bg: 'bg-slate-900/60 border-slate-700/50 text-slate-300',
        };
    }
  };

  const colors = getColors(status);
  const displayLabel = label || status.replace(/_/g, ' ');

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono font-medium border select-none',
        colors.bg,
        className
      )}
    >
      <span
        className={cn(
          'w-1.5 h-1.5 rounded-full',
          colors.dot,
          pulse && 'animate-ping'
        )}
      />
      <span className="capitalize">{displayLabel}</span>
    </span>
  );
};
