import React, { useState, useEffect, useCallback } from 'react';
import {
  Terminal,
  Clock,
  Search,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  FileText,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  Activity,
  Layers,
} from 'lucide-react';
import { api } from '../../api/client';
import { AuditItemResponse } from '../../api/types';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { formatDate } from '../../lib/utils';

export const ActivityLogView: React.FC = () => {
  const [events, setEvents] = useState<AuditItemResponse[]>([]);
  const [category, setCategory] = useState<'all' | 'security_audit' | 'task_event'>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const loadAuditLogs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getAuditEvents(
        category === 'all' ? undefined : category,
        searchQuery.trim() || undefined,
        150
      );
      setEvents(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, [category, searchQuery]);

  useEffect(() => {
    loadAuditLogs();
  }, [loadAuditLogs]);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'succeeded':
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3" />
            <span>{status.toUpperCase()}</span>
          </span>
        );
      case 'failed':
      case 'denied':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <XCircle className="w-3 h-3" />
            <span>{status.toUpperCase()}</span>
          </span>
        );
      case 'pending':
      case 'waiting_approval':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30">
            <Clock className="w-3 h-3" />
            <span>PENDING</span>
          </span>
        );
      case 'running':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-accent-blue/10 text-accent-blue border border-accent-blue/30">
            <Activity className="w-3 h-3 animate-spin" />
            <span>RUNNING</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-surface-raised text-text-secondary border border-border">
            <span>{status.toUpperCase()}</span>
          </span>
        );
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-background">
      {/* Top Header */}
      <div className="p-4 border-b border-border bg-sidebar/50 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-cyan/10 border border-accent-cyan/30 flex items-center justify-center text-accent-cyan">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold font-mono text-text-primary tracking-wide">
                ACTIVITY & AUDIT LOG
              </h1>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-raised text-accent-cyan border border-border">
                IMMUTABLE WAL
              </span>
            </div>
            <p className="text-xs text-text-secondary">
              Real-time audit records of deterministic tool executions, human approvals, and agent step events.
            </p>
          </div>
        </div>

        <Button size="sm" variant="outline" onClick={loadAuditLogs} isLoading={isLoading}>
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </Button>
      </div>

      {error && (
        <div className="p-3 mx-4 mt-3 rounded bg-red-950/30 border border-red-800 text-red-300 text-xs flex items-center gap-2 shrink-0">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="p-4 border-b border-border flex flex-col sm:flex-row items-center justify-between gap-3 shrink-0 bg-surface/30">
        <div className="relative w-full sm:w-80">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search tool, status, or task ID..."
            className="w-full pl-9 pr-3 py-1.5 rounded-md bg-surface border border-border text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-cyan font-sans"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
          <button
            onClick={() => setCategory('all')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono uppercase tracking-wider transition-colors ${
              category === 'all'
                ? 'bg-accent-cyan text-[#080b10] font-bold'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-raised'
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>All Records</span>
          </button>
          <button
            onClick={() => setCategory('security_audit')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono uppercase tracking-wider transition-colors ${
              category === 'security_audit'
                ? 'bg-accent-cyan text-[#080b10] font-bold'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-raised'
            }`}
          >
            <ShieldCheck className="w-3 h-3" />
            <span>Security Audits</span>
          </button>
          <button
            onClick={() => setCategory('task_event')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono uppercase tracking-wider transition-colors ${
              category === 'task_event'
                ? 'bg-accent-cyan text-[#080b10] font-bold'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-raised'
            }`}
          >
            <Terminal className="w-3 h-3" />
            <span>Task Events</span>
          </button>
        </div>
      </div>

      {/* Audit Log Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {events.length === 0 ? (
          <div className="p-12 text-center rounded-xl border border-dashed border-border flex flex-col items-center justify-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-surface-raised border border-border flex items-center justify-center text-text-muted">
              <FileText className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-semibold font-mono text-text-primary">NO AUDIT RECORDS FOUND</h3>
            <p className="text-xs text-text-muted max-w-sm">
              {searchQuery
                ? `No matching events found for "${searchQuery}".`
                : 'Audit logs will appear as tools are executed, plans run, and approvals decided.'}
            </p>
          </div>
        ) : (
          events.map((event) => {
            const isExpanded = expandedIds.has(event.id);
            const isSecurity = event.category === 'security_audit';

            return (
              <Card
                key={event.id}
                className={`transition-all duration-150 border-l-4 ${
                  isSecurity ? 'border-l-accent-cyan' : 'border-l-accent-blue'
                }`}
              >
                <div
                  onClick={() => toggleExpand(event.id)}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 cursor-pointer select-none"
                >
                  <div className="flex items-start sm:items-center gap-2.5 min-w-0">
                    <button className="text-text-muted hover:text-text-primary p-0.5 mt-0.5 sm:mt-0">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-accent-cyan" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </button>

                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs font-bold text-text-primary">
                          {event.title}
                        </span>
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.2 rounded border ${
                            isSecurity
                              ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
                              : 'bg-accent-blue/10 text-accent-blue border-accent-blue/30'
                          }`}
                        >
                          {isSecurity ? 'SECURITY AUDIT' : 'TASK EXECUTION'}
                        </span>
                        {event.task_id && (
                          <span className="text-[10px] font-mono text-text-muted">
                            TASK: {event.task_id.slice(0, 8)}
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] font-mono text-text-muted mt-0.5 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        <span>{formatDate(event.timestamp)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 self-end sm:self-center">
                    {getStatusBadge(event.status)}
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-border space-y-3">
                    <div className="text-xs font-mono text-text-secondary">
                      <span className="text-text-muted">EVENT TYPE:</span>{' '}
                      <span className="text-text-primary">{event.event_type}</span>
                    </div>

                    <div className="space-y-1">
                      <span className="text-xs font-mono text-text-muted">PAYLOAD DETAILS:</span>
                      <pre className="p-3 rounded bg-[#05070a] border border-border text-[11px] font-mono text-accent-cyan overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-80">
                        {JSON.stringify(event.details, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
};
