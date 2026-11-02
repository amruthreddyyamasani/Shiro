/**
 * TypeScript types strictly matching SHIRO FastAPI schemas (shiro/models.py).
 */

export type MemoryCategory = 'preferences' | 'projects' | 'skills' | 'general';

export type TaskStatus =
  | 'planned'
  | 'waiting_approval'
  | 'running'
  | 'paused'
  | 'succeeded'
  | 'failed';

export type TaskStepStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'skipped';

export type ApprovalStatus = 'pending' | 'approved' | 'denied';

export interface HealthResponse {
  status: string;
  model: string;
  ollama_base_url: string;
  thinking_disabled: boolean;
  tools_enabled: boolean;
}

export interface ModelResponse {
  name: string;
  size?: number | null;
  installed: boolean;
  recommended: boolean;
}

export interface ModelRecommendationResponse {
  current_model: string;
  models: ModelResponse[];
}

export interface ConversationResponse {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface MessageResponse {
  id: number;
  conversation_id: string;
  role: 'system' | 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface MessageRequest {
  content: string;
  conversation_id?: string | null;
}

export interface TaskStepResponse {
  id: number;
  task_id: string;
  position: number;
  description: string;
  status: TaskStepStatus;
  attempts: number;
}

export interface TaskResponse {
  id: string;
  title: string;
  status: TaskStatus;
  requires_approval: boolean;
  max_retries: number;
  retry_count: number;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
  steps: TaskStepResponse[];
}

export interface AgentPlanRequest {
  request: string;
  conversation_id?: string | null;
}

export interface AgentPlanResponse {
  task_id: string;
  title: string;
  status: string;
  steps: TaskStepResponse[];
}

export interface AgentRunResponse {
  task_id: string;
  status: string;
  message: string;
  completed_steps: number;
  pending_step_id?: number | null;
}

export interface AgentRunRecordResponse {
  id: number;
  task_id: string;
  task_step_id: number;
  status: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
  started_at: string;
  finished_at?: string | null;
}

export interface ToolDefinitionResponse {
  name: string;
  description: string;
  requires_approval: boolean;
}

export interface ToolApprovalResponse {
  id: string;
  task_id?: string | null;
  step_id?: number | null;
  tool_name: string;
  arguments: Record<string, unknown>;
  affected_resources: string[];
  reason: string;
  status: ApprovalStatus;
  created_at: string;
  expires_at?: string | null;
  decided_at?: string | null;
  consumed_at?: string | null;
}

export type ComputerControlStatus =
  | 'queued'
  | 'observing'
  | 'planning'
  | 'running'
  | 'paused'
  | 'waiting_approval'
  | 'needs_clarification'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'stopped';

export interface ComputerControlState {
  run_id: string;
  task: string;
  status: ComputerControlStatus;
  action_count: number;
  max_actions: number;
  max_duration_seconds: number;
  consecutive_failures: number;
  max_consecutive_failures: number;
  current_action?: Record<string, unknown> | null;
  latest_observation?: Record<string, unknown> | null;
  latest_screenshot?: string | null;
  latest_verification?: Record<string, unknown> | null;
  recent_actions: Array<Record<string, unknown>>;
  approval_id?: string | null;
  error?: string | null;
}

export interface CapabilityResponse {
  name: string;
  status: string;
  description: string;
  execution_enabled: boolean;
}

export interface MemoryResponse {
  id: number;
  category: MemoryCategory;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface MemoryCreateRequest {
  category: MemoryCategory;
  content: string;
}

export interface MemoryUpdateRequest {
  category?: MemoryCategory | null;
  content?: string | null;
}

export interface WebActionResponse {
  id: string;
  method: string;
  url: string;
  reason: string;
  request_body?: string | null;
  status: string;
  note?: string | null;
  created_at: string;
  decided_at?: string | null;
}

export interface ChangeRequestCreateRequest {
  title: string;
  description: string;
  files: string[];
  test_command: string;
  proposed_files: Record<string, string>;
}

export interface ChangeRequestDecisionRequest {
  approved: boolean;
  note?: string | null;
}

export interface ChangeRequestResponse {
  id: string;
  title: string;
  description: string;
  files: string[];
  test_command: string;
  status: string;
  note?: string | null;
  created_at: string;
  decided_at?: string | null;
  diff: string;
  test_status: string;
  test_output?: string | null;
  applied_at?: string | null;
}

export interface AuditItemResponse {
  id: string;
  event_type: 'tool_audit' | 'tool_approval' | 'task_approval' | 'task_run';
  category: 'security_audit' | 'task_event';
  title: string;
  status: string;
  details: Record<string, unknown>;
  task_id?: string | null;
  step_id?: number | null;
  timestamp: string;
}

export interface SystemInfoResponse {
  os_name: string;
  os_version: string;
  os_release: string;
  architecture: string;
  python_version: string;
  database_path: string;
  database_size_bytes: number;
  database_wal_enabled: boolean;
  ollama_base_url: string;
  ollama_model: string;
  ollama_connected: boolean;
  ollama_installed_models: string[];
  app_version: string;
  host: string;
  port: number;
  tools_enabled: boolean;
  personality_mode: string;
  project_root: string;
  approved_roots: string[];
}

export interface SettingsResponse {
  personality_mode: 'adaptive' | 'friendly' | 'professional';
  ollama_model: string;
  ollama_base_url: string;
  database_path: string;
  project_root: string;
  approved_roots: string[];
  max_history_messages: number;
  allow_tools: boolean;
  thinking_enabled: boolean;
  request_timeout_seconds: number;
}

/* Chat Stream NDJSON Event Types */
export interface StreamTokenEvent {
  type: 'token';
  conversation_id: string;
  content: string;
}

export interface StreamDoneEvent {
  type: 'done';
  conversation_id: string;
  content: string;
}

export interface StreamErrorEvent {
  type: 'error';
  conversation_id?: string;
  error: {
    code: string;
    message: string;
  };
}

export type StreamChatEvent = StreamTokenEvent | StreamDoneEvent | StreamErrorEvent;
