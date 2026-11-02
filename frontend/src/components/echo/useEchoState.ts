import { useEffect, useMemo, useRef, useState } from 'react';
import { ComputerControlState, TaskResponse, ToolApprovalResponse } from '../../api/types';
import { EchoState, resolveEchoState } from './echoState';

const DEFAULT_SLEEPY_AFTER_MS = 10 * 60 * 1000;
const CURIOUS_DISPLAY_MS = 1600;
const COMPLETION_DISPLAY_MS = 2600;
const ATTENTION_DISPLAY_MS = 2200;

interface UseEchoStateProps {
  activeTab: string;
  isOnline: boolean;
  isChatStreaming: boolean;
  tasks: TaskResponse[];
  pendingApprovals: ToolApprovalResponse[];
  computerControlState?: ComputerControlState | null;
  sleepyAfterMs?: number;
}

interface TransientState {
  state: EchoState;
  token: number;
}

const EXPLORATION_TABS = new Set(['tools', 'models', 'system', 'memory', 'activity']);

export function useEchoState({
  activeTab,
  isOnline,
  isChatStreaming,
  tasks,
  pendingApprovals,
  computerControlState,
  sleepyAfterMs = DEFAULT_SLEEPY_AFTER_MS,
}: UseEchoStateProps): EchoState {
  const [transientState, setTransientState] = useState<TransientState | null>(null);
  const [activityTick, setActivityTick] = useState(0);
  const [clockTick, setClockTick] = useState(0);
  const lastActivityAt = useRef(Date.now());
  const previousTaskStatuses = useRef<Map<string, TaskResponse['status']> | null>(null);
  const transitionToken = useRef(0);

  const setTransient = (state: EchoState, durationMs: number) => {
    const token = ++transitionToken.current;
    setTransientState({ state, token });
    window.setTimeout(() => {
      setTransientState((current) => (current?.token === token ? null : current));
    }, durationMs);
  };

  const activitySignature = useMemo(() => {
    const taskSignal = tasks
      .map((task) => `${task.id}:${task.status}:${task.steps.map((step) => step.status).join(',')}`)
      .sort()
      .join('|');
    const approvalSignal = pendingApprovals
      .map((approval) => `${approval.id}:${approval.status}`)
      .sort()
      .join('|');
    return [activeTab, isOnline, isChatStreaming, taskSignal, approvalSignal, computerControlState?.run_id, computerControlState?.status].join('::');
  }, [activeTab, computerControlState?.run_id, computerControlState?.status, isChatStreaming, isOnline, pendingApprovals, tasks]);

  useEffect(() => {
    lastActivityAt.current = Date.now();
    setActivityTick((tick) => tick + 1);
  }, [activitySignature]);

  useEffect(() => {
    const wakeEcho = () => {
      lastActivityAt.current = Date.now();
      setActivityTick((tick) => tick + 1);
    };
    window.addEventListener('pointerdown', wakeEcho, { passive: true });
    window.addEventListener('keydown', wakeEcho);
    return () => {
      window.removeEventListener('pointerdown', wakeEcho);
      window.removeEventListener('keydown', wakeEcho);
    };
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => setClockTick((tick) => tick + 1), 30_000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    const currentStatuses = new Map(tasks.map((task) => [task.id, task.status]));
    const previousStatuses = previousTaskStatuses.current;
    if (previousStatuses) {
      const completed = tasks.some(
        (task) => task.status === 'succeeded' && previousStatuses.get(task.id) !== 'succeeded'
      );
      const needsAttention = tasks.some(
        (task) => task.status === 'failed' && previousStatuses.get(task.id) !== 'failed'
      );
      if (completed) {
        setTransient('HAPPY', COMPLETION_DISPLAY_MS);
      } else if (needsAttention) {
        setTransient('CONFUSED', ATTENTION_DISPLAY_MS);
      }
    }
    previousTaskStatuses.current = currentStatuses;
  }, [tasks]);

  useEffect(() => {
    if (EXPLORATION_TABS.has(activeTab)) {
      setTransient('CURIOUS', CURIOUS_DISPLAY_MS);
    } else {
      setTransientState((current) => (current?.state === 'CURIOUS' ? null : current));
    }
  }, [activeTab]);

  const isSleepy =
    activityTick >= 0 &&
    clockTick >= 0 &&
    Date.now() - lastActivityAt.current >= sleepyAfterMs &&
    !isChatStreaming &&
    !tasks.some((task) => task.status === 'running' || task.status === 'planned');

  return resolveEchoState(
    { isOnline, isChatStreaming, tasks, pendingApprovals, computerControlState },
    transientState?.state || null,
    isSleepy
  );
}
