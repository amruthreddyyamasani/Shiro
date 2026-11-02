import React, { useState, useEffect } from 'react';
import { ShieldAlert, Check, X, RefreshCw, AlertCircle } from 'lucide-react';
import { api } from '../../api/client';
import { ToolApprovalResponse, TaskResponse } from '../../api/types';
import { StatusMark } from '../ui/StatusMark';
import { Button } from '../ui/Button';
import { formatDate } from '../../lib/utils';

export const ApprovalCenterView: React.FC = () => {
  const [toolApprovals, setToolApprovals] = useState<ToolApprovalResponse[]>([]);
  const [taskApprovals, setTaskApprovals] = useState<TaskResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadApprovals = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [tApps, allTasks] = await Promise.all([
        api.getToolApprovals('pending'),
        api.getTasks(),
      ]);
      setToolApprovals(tApps);
      setTaskApprovals(allTasks.filter((t) => t.status === 'waiting_approval'));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadApprovals();
  }, []);

  const handleDecideTool = async (approvalId: string, approved: boolean) => {
    try {
      await api.decideToolApproval(approvalId, approved);
      loadApprovals();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleDecideTask = async (taskId: string, approved: boolean) => {
    try {
      await api.approveTask(taskId, approved);
      loadApprovals();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const totalPending = toolApprovals.length + taskApprovals.length;

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-background p-6 space-y-6">
      <div className="flex items-center justify-between pb-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold font-mono text-text-primary tracking-wide">
              APPROVAL CENTER
            </h1>
            <p className="text-xs text-text-secondary">
              Review and authorize protected operations before execution. All authorizations are one-time and expiring.
            </p>
          </div>
        </div>

        <Button size="sm" variant="outline" onClick={loadApprovals} isLoading={isLoading}>
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </Button>
      </div>

      {error && (
        <div className="p-3 rounded bg-red-950/30 border border-red-800 text-red-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {totalPending === 0 ? (
        <div className="p-12 text-center rounded-xl border border-dashed border-border flex flex-col items-center justify-center space-y-3">
          <div className="w-10 h-10 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Check className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-semibold font-mono text-text-primary">NO PENDING APPROVALS</h3>
          <p className="text-xs text-text-muted max-w-sm">
            All agent execution gates are currently clear. When protected file writes or external web searches require authorization, they will appear here.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Tool Approvals Section */}
          {toolApprovals.length > 0 && (
            <div className="space-y-3">
              <span className="text-xs font-mono font-bold text-amber-400 uppercase tracking-wider">
                Protected Tool Operations ({toolApprovals.length})
              </span>

              <div className="grid grid-cols-1 gap-4">
                {toolApprovals.map((appr) => (
                  <div
                    key={appr.id}
                    className="p-4 rounded-lg bg-surface border border-amber-500/40 space-y-3 shadow-md"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                          {appr.tool_name}
                        </span>
                        <span className="text-xs font-mono text-text-muted">
                          ID: {appr.id.slice(0, 8)}...
                        </span>
                      </div>
                      <span className="text-xs font-mono text-text-muted">
                        Requested: {formatDate(appr.created_at)}
                      </span>
                    </div>

                    <div className="space-y-1">
                      <div className="text-xs font-semibold text-text-primary">Reason:</div>
                      <p className="text-xs text-text-secondary bg-surface-raised p-2 rounded border border-border">
                        {appr.reason}
                      </p>
                    </div>

                    <div className="space-y-1">
                      <div className="text-xs font-semibold text-text-primary">Arguments:</div>
                      <pre className="text-xs font-mono text-accent-cyan bg-[#05070a] p-2.5 rounded border border-border overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(appr.arguments, null, 2)}
                      </pre>
                    </div>

                    <div className="flex justify-end gap-3 pt-2 border-t border-border-subtle">
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => handleDecideTool(appr.id, false)}
                      >
                        <X className="w-3.5 h-3.5 mr-1" />
                        <span>Deny Execution</span>
                      </Button>
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => handleDecideTool(appr.id, true)}
                      >
                        <Check className="w-3.5 h-3.5 mr-1" />
                        <span>Authorize Once</span>
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Task Plan Approvals Section */}
          {taskApprovals.length > 0 && (
            <div className="space-y-3">
              <span className="text-xs font-mono font-bold text-accent-blue uppercase tracking-wider">
                Full Task Plans Waiting Approval ({taskApprovals.length})
              </span>

              <div className="grid grid-cols-1 gap-4">
                {taskApprovals.map((task) => (
                  <div
                    key={task.id}
                    className="p-4 rounded-lg bg-surface border border-accent-blue/40 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-text-primary">{task.title}</h3>
                      <StatusMark status={task.status} />
                    </div>

                    <div className="space-y-1.5">
                      <span className="text-xs font-mono text-text-muted uppercase">Steps:</span>
                      {task.steps.map((s, idx) => (
                        <div
                          key={s.id}
                          className="text-xs text-text-secondary pl-3 border-l-2 border-border flex items-center justify-between"
                        >
                          <span>
                            {idx + 1}. {s.description}
                          </span>
                        </div>
                      ))}
                    </div>

                    <div className="flex justify-end gap-3 pt-2 border-t border-border-subtle">
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => handleDecideTask(task.id, false)}
                      >
                        Deny Plan
                      </Button>
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => handleDecideTask(task.id, true)}
                      >
                        Approve Plan
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
