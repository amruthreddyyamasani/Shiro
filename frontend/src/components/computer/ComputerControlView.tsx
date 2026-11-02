import React, { useEffect, useState } from 'react';
import { Camera, Pause, Play, ShieldAlert, Square, TriangleAlert } from 'lucide-react';
import { api } from '../../api/client';
import { ComputerControlState } from '../../api/types';
import { Button } from '../ui/Button';
import { Card, CardHeader, CardTitle } from '../ui/Card';

interface ComputerControlViewProps {
  onStateChange?: (state: ComputerControlState | null) => void;
}

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled', 'stopped']);

export const ComputerControlView: React.FC<ComputerControlViewProps> = ({ onStateChange }) => {
  const [task, setTask] = useState('');
  const [state, setState] = useState<ComputerControlState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (next: ComputerControlState | null) => {
    setState(next);
    onStateChange?.(next);
  };

  useEffect(() => {
    if (!state || TERMINAL.has(state.status)) return;
    const timer = window.setInterval(async () => {
      try {
        update(await api.getComputerControlTask(state.run_id));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not read computer-control state');
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [state?.run_id, state?.status]);

  const start = async () => {
    if (!task.trim()) return;
    setBusy(true);
    setError(null);
    try {
      update(await api.createComputerControlTask({ task: task.trim() }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start computer control');
    } finally {
      setBusy(false);
    }
  };

  const mutate = async (operation: () => Promise<ComputerControlState>) => {
    if (!state) return;
    setBusy(true);
    try {
      update(await operation());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Computer-control request failed');
    } finally {
      setBusy(false);
    }
  };

  const emergencyStop = async () => {
    setBusy(true);
    try {
      await api.emergencyStopComputerControl();
      if (state) update(await api.getComputerControlTask(state.run_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Emergency stop failed');
    } finally {
      setBusy(false);
    }
  };

  const status = state?.status || 'idle';
  const verification = state?.latest_verification;

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-5">
      <div>
        <div className="text-[11px] text-accent-cyan font-mono tracking-widest uppercase">Milestone C</div>
        <h1 className="text-2xl font-semibold text-text-primary mt-1">Computer Control</h1>
        <p className="text-sm text-text-muted mt-1">Observe, understand, validate, act, observe again, verify.</p>
      </div>

      <Card variant="raised">
        <CardHeader>
          <CardTitle>Bounded visual task</CardTitle>
          <span className="text-[11px] font-mono text-text-muted">LOCAL ONLY</span>
        </CardHeader>
        <div className="flex gap-2">
          <input
            value={task}
            onChange={(event) => setTask(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && void start()}
            placeholder="e.g. Open Notepad and type a short project summary"
            className="flex-1 min-w-0 rounded-md bg-surface border border-border px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-cyan"
            disabled={Boolean(state && !TERMINAL.has(state.status))}
          />
          <Button variant="primary" onClick={() => void start()} disabled={busy || !task.trim() || Boolean(state && !TERMINAL.has(state.status))}>
            <Play className="w-4 h-4" /> Start
          </Button>
        </div>
        {error && <div className="mt-3 text-sm text-red-400">{error}</div>}
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2" variant="raised">
          <CardHeader>
            <CardTitle><Camera className="inline w-4 h-4 mr-2" />Latest screenshot</CardTitle>
            <span className="text-xs font-mono text-text-muted uppercase">{status}</span>
          </CardHeader>
          {state?.latest_screenshot ? (
            <img src={state.latest_screenshot} alt="Latest local desktop observation" className="w-full max-h-[460px] object-contain rounded border border-border bg-black" />
          ) : (
            <div className="h-48 rounded border border-dashed border-border flex items-center justify-center text-sm text-text-muted">No observation yet</div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => state && void mutate(() => api.pauseComputerControlTask(state.run_id))} disabled={!state || busy || TERMINAL.has(state.status)}><Pause className="w-3.5 h-3.5" /> Pause</Button>
            <Button size="sm" onClick={() => state && void mutate(() => api.resumeComputerControlTask(state.run_id))} disabled={!state || busy || TERMINAL.has(state.status)}><Play className="w-3.5 h-3.5" /> Resume</Button>
            <Button size="sm" variant="secondary" onClick={() => state && void mutate(() => api.cancelComputerControlTask(state.run_id))} disabled={!state || busy || TERMINAL.has(state.status)}><Square className="w-3.5 h-3.5" /> Cancel</Button>
            <Button size="sm" variant="danger" onClick={() => void emergencyStop()} disabled={busy}><ShieldAlert className="w-3.5 h-3.5" /> Emergency stop</Button>
          </div>
        </Card>

        <Card variant="raised">
          <CardHeader><CardTitle>Execution status</CardTitle></CardHeader>
          <div className="space-y-3 text-sm">
            <div><div className="text-[10px] text-text-muted uppercase font-mono">Current task</div><div className="mt-1 text-text-primary">{state?.task || '—'}</div></div>
            <div><div className="text-[10px] text-text-muted uppercase font-mono">Planned action</div><pre className="mt-1 whitespace-pre-wrap break-words text-xs text-accent-cyan">{state?.current_action ? JSON.stringify(state.current_action, null, 2) : '—'}</pre></div>
            <div><div className="text-[10px] text-text-muted uppercase font-mono">Verification</div><pre className="mt-1 whitespace-pre-wrap break-words text-xs text-text-secondary">{verification ? JSON.stringify(verification, null, 2) : '—'}</pre></div>
            {state?.approval_id && <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-amber-300 text-xs"><TriangleAlert className="inline w-3.5 h-3.5 mr-1" />Approval requested: {state.approval_id}</div>}
            {state?.error && <div className="rounded border border-red-500/30 bg-red-500/10 p-2 text-red-300 text-xs">{state.error}</div>}
          </div>
        </Card>
      </div>

      <Card variant="raised">
        <CardHeader><CardTitle>Recent actions</CardTitle><span className="text-xs font-mono text-text-muted">{state?.action_count || 0} / {state?.max_actions || 15}</span></CardHeader>
        {state?.recent_actions?.length ? (
          <div className="space-y-2">{state.recent_actions.map((item, index) => <pre key={index} className="rounded bg-surface p-2 text-xs text-text-secondary overflow-x-auto">{JSON.stringify(item, null, 2)}</pre>)}</div>
        ) : <div className="text-sm text-text-muted">No actions have been completed.</div>}
      </Card>
    </div>
  );
};
