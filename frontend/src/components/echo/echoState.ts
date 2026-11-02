import { TaskResponse, ToolApprovalResponse } from '../../api/types';
import { ComputerControlState } from '../../api/types';

export const ECHO_STATES = [
  'IDLE',
  'CURIOUS',
  'THINKING',
  'WORKING',
  'HAPPY',
  'CONFUSED',
  'SLEEPY',
  'DISCONNECTED',
] as const;

export type EchoState = (typeof ECHO_STATES)[number];

export interface EchoStateSnapshot {
  isOnline: boolean;
  isChatStreaming: boolean;
  tasks: TaskResponse[];
  pendingApprovals: ToolApprovalResponse[];
  computerControlState?: ComputerControlState | null;
}

export function resolveEchoState(
  snapshot: EchoStateSnapshot,
  transientState: EchoState | null,
  isSleepy: boolean
): EchoState {
  if (!snapshot.isOnline) return 'DISCONNECTED';
  const computer = snapshot.computerControlState;
  if (computer && ['observing', 'planning'].includes(computer.status)) return 'THINKING';
  if (computer && computer.status === 'running') return 'WORKING';
  if (computer && computer.status === 'succeeded') return 'HAPPY';
  if (computer && ['needs_clarification', 'waiting_approval', 'failed'].includes(computer.status)) return 'CONFUSED';
  if (snapshot.isChatStreaming) return 'THINKING';
  if (snapshot.tasks.some((task) => task.status === 'running')) return 'WORKING';
  if (snapshot.tasks.some((task) => task.status === 'planned')) return 'THINKING';
  if (transientState) return transientState;
  if (snapshot.pendingApprovals.length > 0 || snapshot.tasks.some((task) => task.status === 'waiting_approval')) {
    return 'IDLE';
  }
  return isSleepy ? 'SLEEPY' : 'IDLE';
}

export function echoStateLabel(state: EchoState): string {
  switch (state) {
    case 'IDLE':
      return 'Waiting';
    case 'CURIOUS':
      return 'Exploring';
    case 'THINKING':
      return 'Thinking';
    case 'WORKING':
      return 'Working';
    case 'HAPPY':
      return 'Completed';
    case 'CONFUSED':
      return 'Needs attention';
    case 'SLEEPY':
      return 'Idle';
    case 'DISCONNECTED':
      return 'Backend unavailable';
  }
}
