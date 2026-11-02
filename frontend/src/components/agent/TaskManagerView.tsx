import React, { useState, useEffect } from 'react';
import {
  CheckSquare,
  Play,
  Pause,
  RotateCcw,
  XCircle,
  Clock,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Plus,
} from 'lucide-react';
import { api } from '../../api/client';
import { TaskResponse } from '../../api/types';
import { StatusMark } from '../ui/StatusMark';
import { Button } from '../ui/Button';
import { formatDate } from '../../lib/utils';

export const TaskManagerView: React.FC = () => {
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [selectedTask, setSelectedTask] = useState<TaskResponse | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [newPlanPrompt, setNewPlanPrompt] = useState<string>('');
  const [isPlanning, setIsPlanning] = useState<boolean>(false);
  const [showPlanModal, setShowPlanModal] = useState<boolean>(false);

  const loadTasks = async () => {
    setIsLoading(true);
    setActionError(null);
    try {
      const data = await api.getTasks();
      setTasks(data);
      if (selectedTask) {
        const refreshed = data.find((t) => t.id === selectedTask.id);
        if (refreshed) setSelectedTask(refreshed);
      }
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
  }, []);

  const handleApprove = async (taskId: string, approved: boolean) => {
    try {
      await api.approveTask(taskId, approved);
      loadTasks();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleRun = async (taskId: string) => {
    try {
      await api.runTaskBackground(taskId);
      loadTasks();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const handlePause = async (taskId: string) => {
    try {
      await api.pauseTask(taskId);
      loadTasks();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleResume = async (taskId: string) => {
    try {
      await api.resumeTask(taskId);
      loadTasks();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleCancel = async (taskId: string) => {
    try {
      await api.cancelTask(taskId);
      loadTasks();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleCreatePlan = async () => {
    if (!newPlanPrompt.trim()) return;
    setIsPlanning(true);
    setActionError(null);
    try {
      const planRes = await api.planTask({ request: newPlanPrompt });
      setNewPlanPrompt('');
      setShowPlanModal(false);
      await loadTasks();
      const created = tasks.find((t) => t.id === planRes.task_id);
      if (created) setSelectedTask(created);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsPlanning(false);
    }
  };

  const filteredTasks = tasks.filter((t) => {
    if (filter === 'all') return true;
    return t.status === filter;
  });

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-background">
      {/* Top Bar */}
      <div className="p-4 border-b border-border bg-sidebar/50 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <CheckSquare className="w-5 h-5 text-accent-blue" />
          <div>
            <h1 className="text-base font-bold font-mono text-text-primary">TASK MANAGER</h1>
            <p className="text-xs text-text-secondary">
              Inspect structured agent plans, supervise approvals, and monitor step execution.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={loadTasks} isLoading={isLoading}>
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
          <Button size="sm" variant="primary" onClick={() => setShowPlanModal(true)}>
            <Plus className="w-3.5 h-3.5" />
            <span>Synthesize Plan</span>
          </Button>
        </div>
      </div>

      {actionError && (
        <div className="p-3 mx-4 mt-3 rounded bg-red-950/30 border border-red-800 text-red-300 text-xs flex items-center justify-between shrink-0">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="text-xs hover:underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="px-4 py-2 border-b border-border flex items-center gap-2 overflow-x-auto shrink-0 bg-surface/30">
        {[
          { id: 'all', label: 'All Tasks' },
          { id: 'waiting_approval', label: 'Waiting Approval' },
          { id: 'planned', label: 'Planned' },
          { id: 'running', label: 'Running' },
          { id: 'paused', label: 'Paused' },
          { id: 'succeeded', label: 'Succeeded' },
          { id: 'failed', label: 'Failed' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setFilter(tab.id)}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors whitespace-nowrap ${
              filter === tab.id
                ? 'bg-accent-blue text-white font-bold'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-raised'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Main Split Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Task List */}
        <div className="w-full md:w-1/2 p-4 overflow-y-auto space-y-3 border-r border-border">
          {filteredTasks.length === 0 ? (
            <div className="p-8 text-center text-xs text-text-muted">
              No tasks matching "{filter}".
            </div>
          ) : (
            filteredTasks.map((task) => (
              <div
                key={task.id}
                onClick={() => setSelectedTask(task)}
                className={`p-3.5 rounded-lg border cursor-pointer transition-colors space-y-2 ${
                  selectedTask?.id === task.id
                    ? 'bg-surface-elevated border-accent-blue'
                    : 'bg-surface border-border hover:border-border-hover'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-text-muted">
                    ID: {task.id.slice(0, 8)}...
                  </span>
                  <StatusMark status={task.status} />
                </div>

                <h3 className="text-sm font-semibold text-text-primary line-clamp-1">
                  {task.title}
                </h3>

                <div className="flex items-center justify-between text-xs text-text-muted font-mono pt-1 border-t border-border-subtle">
                  <span>Steps: {task.steps.length}</span>
                  <span>{formatDate(task.created_at)}</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Task Details Drawer */}
        <div className="hidden md:flex flex-1 flex-col overflow-y-auto p-4 bg-surface/30">
          {selectedTask ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <div>
                  <h2 className="text-base font-bold text-text-primary">{selectedTask.title}</h2>
                  <span className="text-xs font-mono text-text-muted">ID: {selectedTask.id}</span>
                </div>
                <StatusMark status={selectedTask.status} />
              </div>

              {/* Action Toolbar */}
              <div className="flex items-center gap-2 p-2.5 rounded bg-surface-raised border border-border">
                {selectedTask.status === 'waiting_approval' && (
                  <>
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => handleApprove(selectedTask.id, true)}
                    >
                      Approve Task
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => handleApprove(selectedTask.id, false)}
                    >
                      Deny
                    </Button>
                  </>
                )}

                {selectedTask.status === 'planned' && (
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => handleRun(selectedTask.id)}
                  >
                    <Play className="w-3.5 h-3.5 mr-1" />
                    <span>Run Task</span>
                  </Button>
                )}

                {selectedTask.status === 'running' && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handlePause(selectedTask.id)}
                  >
                    <Pause className="w-3.5 h-3.5 mr-1" />
                    <span>Pause</span>
                  </Button>
                )}

                {selectedTask.status === 'paused' && (
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => handleResume(selectedTask.id)}
                  >
                    <RotateCcw className="w-3.5 h-3.5 mr-1" />
                    <span>Resume</span>
                  </Button>
                )}

                {(selectedTask.status === 'planned' ||
                  selectedTask.status === 'running' ||
                  selectedTask.status === 'paused' ||
                  selectedTask.status === 'waiting_approval') && (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => handleCancel(selectedTask.id)}
                  >
                    <XCircle className="w-3.5 h-3.5 mr-1" />
                    <span>Cancel</span>
                  </Button>
                )}
              </div>

              {/* Error notice if last_error */}
              {selectedTask.last_error && (
                <div className="p-3 rounded bg-red-950/30 border border-red-800 text-red-300 text-xs flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold">Execution Error: </span>
                    {selectedTask.last_error}
                  </div>
                </div>
              )}

              {/* Steps Checklist */}
              <div className="space-y-2">
                <span className="text-xs font-mono font-semibold uppercase text-text-muted">
                  Structured Execution Steps ({selectedTask.steps.length})
                </span>

                <div className="space-y-2">
                  {selectedTask.steps.map((step) => (
                    <div
                      key={step.id}
                      className="p-3 rounded-lg bg-surface border border-border space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {step.status === 'succeeded' ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          ) : (
                            <Clock className="w-4 h-4 text-text-muted" />
                          )}
                          <span className="font-mono text-xs font-semibold text-text-primary">
                            Step {step.position + 1}
                          </span>
                        </div>
                        <StatusMark status={step.status} />
                      </div>

                      <p className="text-xs text-text-secondary pl-6 leading-relaxed">
                        {step.description}
                      </p>

                      <div className="pl-6 text-[11px] font-mono text-text-muted">
                        Attempts: {step.attempts}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-text-muted">
              Select a task from the left to inspect details.
            </div>
          )}
        </div>
      </div>

      {/* Synthesize Plan Modal */}
      {showPlanModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-surface-elevated border border-border rounded-xl p-5 space-y-4 shadow-2xl">
            <h3 className="text-sm font-bold font-mono uppercase tracking-wider text-text-primary">
              Synthesize New Task Plan
            </h3>
            <p className="text-xs text-text-secondary">
              Instruct SHIRO's task planner to generate an approved, structured sequence of tool actions.
            </p>

            <textarea
              value={newPlanPrompt}
              onChange={(e) => setNewPlanPrompt(e.target.value)}
              placeholder="e.g. Inspect all python files in workspace and compute line count..."
              rows={4}
              className="w-full p-3 rounded-md bg-surface-input border border-border text-xs text-text-primary focus:outline-none focus:border-accent-cyan resize-none font-sans"
            />

            <div className="flex justify-end gap-2 pt-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowPlanModal(false)}
                disabled={isPlanning}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                variant="primary"
                onClick={handleCreatePlan}
                isLoading={isPlanning}
                disabled={!newPlanPrompt.trim()}
              >
                Synthesize Plan
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
