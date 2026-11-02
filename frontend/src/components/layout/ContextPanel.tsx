import React from 'react';
import { X, ShieldAlert, Activity, Clock, CheckCircle2 } from 'lucide-react';
import { TaskResponse, ToolApprovalResponse } from '../../api/types';
import { formatDate } from '../../lib/utils';
import { StatusMark } from '../ui/StatusMark';
import { Button } from '../ui/Button';

interface ContextPanelProps {
  isOpen: boolean;
  onClose: () => void;
  activeTask?: TaskResponse | null;
  pendingApprovals: ToolApprovalResponse[];
  onDecideApproval: (approvalId: string, approved: boolean) => void;
  ollamaBaseUrl: string;
  activeModel: string;
}

export const ContextPanel: React.FC<ContextPanelProps> = ({
  isOpen,
  onClose,
  activeTask,
  pendingApprovals,
  onDecideApproval,
  ollamaBaseUrl,
  activeModel,
}) => {
  if (!isOpen) return null;

  return (
    <aside className="w-80 border-l border-border bg-surface flex flex-col h-screen shrink-0 animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="p-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-accent-cyan" />
          <span className="text-xs font-mono font-semibold uppercase tracking-wider text-text-primary">
            Context & Tasks
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface-raised"
          title="Close Panel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-3 overflow-y-auto space-y-4 flex-1">
        {/* Pending Approvals Section */}
        {pendingApprovals.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-mono font-bold text-amber-400">
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>APPROVALS PENDING ({pendingApprovals.length})</span>
            </div>
            <div className="space-y-2">
              {pendingApprovals.map((appr) => (
                <div
                  key={appr.id}
                  className="p-2.5 rounded bg-amber-950/20 border border-amber-800/40 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-semibold text-amber-300">
                      {appr.tool_name}
                    </span>
                    <span className="text-[10px] text-text-muted font-mono">
                      {formatDate(appr.created_at)}
                    </span>
                  </div>
                  <p className="text-xs text-text-secondary leading-tight">{appr.reason}</p>
                  <div className="flex gap-2 pt-1">
                    <Button
                      size="sm"
                      variant="primary"
                      className="flex-1 text-[11px] py-1 h-auto"
                      onClick={() => onDecideApproval(appr.id, true)}
                    >
                      Authorize
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      className="flex-1 text-[11px] py-1 h-auto"
                      onClick={() => onDecideApproval(appr.id, false)}
                    >
                      Deny
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Active Task Section */}
        <div className="space-y-2">
          <div className="text-xs font-mono font-semibold text-text-muted uppercase tracking-wider">
            Active Task Engine
          </div>
          {activeTask ? (
            <div className="p-3 rounded-lg bg-surface-raised border border-border space-y-3">
              <div className="flex items-center justify-between">
                <StatusMark status={activeTask.status} />
                <span className="text-[10px] font-mono text-text-muted">
                  Retries: {activeTask.retry_count}/{activeTask.max_retries}
                </span>
              </div>
              <h4 className="text-xs font-medium text-text-primary">{activeTask.title}</h4>
              <div className="space-y-1.5 pt-1 border-t border-border-subtle">
                <span className="text-[10px] font-mono text-text-muted uppercase">Plan Steps</span>
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {activeTask.steps.map((st) => (
                    <div
                      key={st.id}
                      className="flex items-start gap-2 text-xs p-1 rounded bg-surface border border-border-subtle"
                    >
                      {st.status === 'succeeded' ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                      ) : (
                        <Clock className="w-3.5 h-3.5 text-text-muted shrink-0 mt-0.5" />
                      )}
                      <span className="text-[11px] text-text-secondary leading-tight truncate">
                        {st.description}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-lg border border-dashed border-border-subtle text-center text-xs text-text-muted">
              No active task executing
            </div>
          )}
        </div>

        {/* System & Hardware Environment */}
        <div className="space-y-2 pt-2 border-t border-border">
          <div className="text-xs font-mono font-semibold text-text-muted uppercase tracking-wider">
            Inference Environment
          </div>
          <div className="p-2.5 rounded bg-surface-raised border border-border space-y-2 text-xs font-mono">
            <div className="flex justify-between items-center text-text-secondary">
              <span>Endpoint:</span>
              <span className="text-text-primary text-[11px]">{ollamaBaseUrl}</span>
            </div>
            <div className="flex justify-between items-center text-text-secondary">
              <span>Model:</span>
              <span className="text-accent-cyan text-[11px] font-bold">{activeModel}</span>
            </div>
            <div className="flex justify-between items-center text-text-secondary">
              <span>Cloud AI:</span>
              <span className="text-emerald-400 text-[11px]">Strictly Disabled</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};
