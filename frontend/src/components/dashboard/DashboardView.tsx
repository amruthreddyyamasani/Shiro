import React, { useEffect, useState } from 'react';
import {
  Activity,
  Cpu,
  ShieldAlert,
  CheckSquare,
  MessageSquare,
  Brain,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import { api } from '../../api/client';
import {
  HealthResponse,
  ModelResponse,
  CapabilityResponse,
  TaskResponse,
  ToolApprovalResponse,
} from '../../api/types';
import { Card, CardHeader, CardTitle } from '../ui/Card';
import { StatusMark } from '../ui/StatusMark';
import { Button } from '../ui/Button';
import { formatBytes } from '../../lib/utils';
import { NavTab } from '../layout/Sidebar';

interface DashboardViewProps {
  onNavigate: (tab: NavTab) => void;
  onNewChat: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({ onNavigate, onNewChat }) => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [models, setModels] = useState<ModelResponse[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityResponse[]>([]);
  const [resumableTasks, setResumableTasks] = useState<TaskResponse[]>([]);
  const [allTasks, setAllTasks] = useState<TaskResponse[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<ToolApprovalResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [h, m, c, rTasks, tasks, approvals] = await Promise.all([
        api.getHealth(),
        api.getModelRecommendations().catch(() => ({ current_model: 'unknown', models: [] })),
        api.getCapabilities().catch(() => []),
        api.getResumableTasks().catch(() => []),
        api.getTasks().catch(() => []),
        api.getToolApprovals('pending').catch(() => []),
      ]);

      setHealth(h);
      setModels(m.models);
      setCapabilities(c);
      setResumableTasks(rTasks);
      setAllTasks(tasks);
      setPendingApprovals(approvals);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Top Welcome & Actions */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 pb-4 border-b border-border">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h1 className="text-xl font-bold font-mono tracking-tight text-text-primary">
              OPERATING ENVIRONMENT
            </h1>
            <span className="text-xs px-2 py-0.5 rounded bg-surface-raised border border-border text-accent-cyan font-mono whitespace-nowrap">
              LOCAL-FIRST
            </span>
          </div>
          <p className="text-xs text-text-secondary break-words">
            Deterministic agentic runtime powered by local Ollama inference and SQLite durability.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" onClick={loadData} isLoading={isLoading}>
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
          <Button variant="primary" size="sm" onClick={onNewChat}>
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Start Chat</span>
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-md bg-red-950/30 border border-red-800 text-red-300 text-xs flex items-center justify-between">
          <span>Failed to connect to SHIRO backend: {error}</span>
          <Button size="sm" variant="danger" onClick={loadData}>
            Retry
          </Button>
        </div>
      )}

      {/* Resumable Tasks Notice if any */}
      {resumableTasks.length > 0 && (
        <div className="p-4 rounded-lg bg-accent-blue/10 border border-accent-blue/30 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-accent-blue/20 flex items-center justify-center text-accent-blue">
              <Activity className="w-4 h-4 animate-spin" />
            </div>
            <div>
              <div className="text-xs font-mono font-bold text-accent-blue">
                {resumableTasks.length} RESUMABLE TASK(S) DETECTED
              </div>
              <div className="text-xs text-text-secondary">
                Tasks from a previous session or restart are ready to resume.
              </div>
            </div>
          </div>
          <Button size="sm" variant="secondary" onClick={() => onNavigate('tasks')}>
            Open Task Manager
          </Button>
        </div>
      )}

      {/* 4 Core Operational Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Backend & Ollama Status */}
        <Card>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono text-text-muted uppercase">SYSTEM STATUS</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-lg font-bold font-mono text-text-primary flex items-center gap-2">
            <span>{health ? 'OPERATIONAL' : 'CONNECTING...'}</span>
          </div>
          <div className="mt-2 text-xs text-text-secondary flex items-center justify-between font-mono">
            <span>Host: 127.0.0.1</span>
            <StatusMark status={health?.status === 'ok' ? 'ok' : 'offline'} />
          </div>
        </Card>

        {/* Current Model */}
        <Card>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono text-text-muted uppercase">ACTIVE MODEL</span>
            <Cpu className="w-4 h-4 text-accent-cyan" />
          </div>
          <div className="text-lg font-bold font-mono text-accent-cyan truncate">
            {health?.model || 'shiro:latest'}
          </div>
          <div className="mt-2 text-xs text-text-secondary flex items-center justify-between font-mono">
            <span>Thinking: Disabled</span>
            <span className="text-[10px] text-text-muted">Local</span>
          </div>
        </Card>

        {/* Active Tasks */}
        <Card
          className="cursor-pointer hover:border-border-hover transition-colors"
          onClick={() => onNavigate('tasks')}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono text-text-muted uppercase">TASKS RUNNING</span>
            <CheckSquare className="w-4 h-4 text-accent-blue" />
          </div>
          <div className="text-lg font-bold font-mono text-text-primary">
            {allTasks.filter((t) => t.status === 'running' || t.status === 'planned').length}
          </div>
          <div className="mt-2 text-xs text-text-secondary flex items-center justify-between font-mono">
            <span>Total Logged: {allTasks.length}</span>
            <span className="text-accent-blue hover:underline">View All &rarr;</span>
          </div>
        </Card>

        {/* Pending Approvals */}
        <Card
          className={`cursor-pointer transition-colors ${
            pendingApprovals.length > 0
              ? 'border-amber-500/50 bg-amber-950/10'
              : 'hover:border-border-hover'
          }`}
          onClick={() => onNavigate('approvals')}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono text-text-muted uppercase">PENDING APPROVALS</span>
            <ShieldAlert
              className={`w-4 h-4 ${pendingApprovals.length > 0 ? 'text-amber-400' : 'text-text-muted'}`}
            />
          </div>
          <div
            className={`text-lg font-bold font-mono ${
              pendingApprovals.length > 0 ? 'text-amber-400' : 'text-text-primary'
            }`}
          >
            {pendingApprovals.length}
          </div>
          <div className="mt-2 text-xs text-text-secondary flex items-center justify-between font-mono">
            <span>Security Gates</span>
            <span className="text-amber-400 hover:underline">Review &rarr;</span>
          </div>
        </Card>
      </div>

      {/* Installed Models & Capabilities Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Installed Local Models */}
        <Card>
          <CardHeader>
            <CardTitle>Installed Ollama Models</CardTitle>
            <span className="text-[10px] font-mono text-text-muted">READ-ONLY LOCAL REGISTRY</span>
          </CardHeader>
          <div className="space-y-2">
            {models.length > 0 ? (
              models.map((m) => (
                <div
                  key={m.name}
                  className="p-2.5 rounded bg-surface-raised border border-border flex items-center justify-between text-xs font-mono"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-text-primary">{m.name}</span>
                    {m.recommended && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-cyan/10 border border-accent-cyan/30 text-accent-cyan">
                        Default
                      </span>
                    )}
                  </div>
                  <span className="text-text-muted text-[11px]">{formatBytes(m.size)}</span>
                </div>
              ))
            ) : (
              <div className="text-xs text-text-muted p-4 text-center">
                Querying local Ollama /api/tags...
              </div>
            )}
          </div>
        </Card>

        {/* Security Capabilities */}
        <Card>
          <CardHeader>
            <CardTitle>System Execution Boundaries</CardTitle>
            <span className="text-[10px] font-mono text-text-muted">SAFETY CONSTRAINTS</span>
          </CardHeader>
          <div className="space-y-2">
            {capabilities.map((c) => (
              <div
                key={c.name}
                className="p-2.5 rounded bg-surface-raised border border-border flex items-center justify-between text-xs"
              >
                <div className="space-y-0.5">
                  <div className="font-mono font-medium text-text-primary">{c.name}</div>
                  <div className="text-[11px] text-text-muted">{c.description}</div>
                </div>
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                    c.execution_enabled
                      ? 'bg-emerald-950/40 text-emerald-400 border-emerald-800/40'
                      : 'bg-surface text-text-muted border-border'
                  }`}
                >
                  {c.status}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Quick Navigation Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-2">
        <div
          onClick={() => onNavigate('chat')}
          className="p-4 rounded-lg bg-surface border border-border hover:border-accent-cyan/50 cursor-pointer transition-colors space-y-1 group"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold text-text-primary group-hover:text-accent-cyan transition-colors">
              CONVERSATIONAL CHAT
            </span>
            <MessageSquare className="w-4 h-4 text-accent-cyan" />
          </div>
          <p className="text-xs text-text-secondary">
            Continuous local chat with streaming tokens, personality controls, and memory.
          </p>
        </div>

        <div
          onClick={() => onNavigate('activity')}
          className="p-4 rounded-lg bg-surface border border-border hover:border-accent-cyan/50 cursor-pointer transition-colors space-y-1 group"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold text-text-primary group-hover:text-accent-cyan transition-colors">
              ACTIVITY & AUDIT LOG
            </span>
            <Activity className="w-4 h-4 text-accent-cyan" />
          </div>
          <p className="text-xs text-text-secondary">
            Verify tool execution audits, approval events, and agent step execution runs.
          </p>
        </div>

        <div
          onClick={() => onNavigate('improvement')}
          className="p-4 rounded-lg bg-surface border border-border hover:border-accent-violet/50 cursor-pointer transition-colors space-y-1 group"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold text-text-primary group-hover:text-accent-violet transition-colors">
              CODE REVIEW
            </span>
            <Brain className="w-4 h-4 text-accent-violet" />
          </div>
          <p className="text-xs text-text-secondary">
            Inspect staged codebase diffs, test sandbox harnesses, and manage rollback snapshots.
          </p>
        </div>

        <div
          onClick={() => onNavigate('system')}
          className="p-4 rounded-lg bg-surface border border-border hover:border-accent-blue/50 cursor-pointer transition-colors space-y-1 group"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold text-text-primary group-hover:text-accent-blue transition-colors">
              SYSTEM & WINDOWS INFO
            </span>
            <Cpu className="w-4 h-4 text-accent-blue" />
          </div>
          <p className="text-xs text-text-secondary">
            Inspect verified host OS, Python, Ollama daemon, and SQLite database storage.
          </p>
        </div>
      </div>
    </div>
  );
};
