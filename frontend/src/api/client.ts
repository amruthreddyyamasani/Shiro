/**
 * Centralized typed API client for SHIRO FastAPI backend.
 */
import {
  HealthResponse,
  ModelRecommendationResponse,
  CapabilityResponse,
  ToolDefinitionResponse,
  ToolApprovalResponse,
  TaskResponse,
  AgentPlanResponse,
  AgentPlanRequest,
  AgentRunResponse,
  AgentRunRecordResponse,
  ConversationResponse,
  MessageResponse,
  MemoryResponse,
  MemoryCreateRequest,
  MemoryUpdateRequest,
  WebActionResponse,
  ChangeRequestResponse,
  ChangeRequestCreateRequest,
  ChangeRequestDecisionRequest,
  AuditItemResponse,
  SystemInfoResponse,
  SettingsResponse,
  ComputerControlState,
} from './types';

class ApiClient {
  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(endpoint, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      let detail = `Error ${response.status}: ${response.statusText}`;
      try {
        const errorData = await response.json();
        if (errorData.detail) detail = errorData.detail;
      } catch {
        // use default detail
      }
      throw new Error(detail);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  // System
  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/healthz');
  }

  // Models
  async getModelRecommendations(): Promise<ModelRecommendationResponse> {
    return this.request<ModelRecommendationResponse>('/v1/models/recommend');
  }

  // Capabilities
  async getCapabilities(): Promise<CapabilityResponse[]> {
    return this.request<CapabilityResponse[]>('/v1/capabilities');
  }

  // Tools
  async getTools(): Promise<ToolDefinitionResponse[]> {
    return this.request<ToolDefinitionResponse[]>('/v1/tools');
  }

  async getToolApprovals(status?: 'pending' | 'approved' | 'denied'): Promise<ToolApprovalResponse[]> {
    const query = status ? `?status=${status}` : '';
    return this.request<ToolApprovalResponse[]>(`/v1/tool-approvals${query}`);
  }

  async decideToolApproval(approvalId: string, approved: boolean): Promise<ToolApprovalResponse> {
    return this.request<ToolApprovalResponse>(`/v1/tool-approvals/${approvalId}/decide`, {
      method: 'POST',
      body: JSON.stringify({ approved }),
    });
  }

  async createComputerControlTask(request: {
    task: string;
    max_actions?: number;
    max_duration_seconds?: number;
    max_consecutive_failures?: number;
  }): Promise<ComputerControlState> {
    return this.request<ComputerControlState>('/v1/computer-control/tasks', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getComputerControlTask(runId: string): Promise<ComputerControlState> {
    return this.request<ComputerControlState>(`/v1/computer-control/tasks/${runId}`);
  }

  async pauseComputerControlTask(runId: string): Promise<ComputerControlState> {
    return this.request<ComputerControlState>(`/v1/computer-control/tasks/${runId}/pause`, { method: 'POST' });
  }

  async resumeComputerControlTask(runId: string): Promise<ComputerControlState> {
    return this.request<ComputerControlState>(`/v1/computer-control/tasks/${runId}/resume`, { method: 'POST' });
  }

  async cancelComputerControlTask(runId: string): Promise<ComputerControlState> {
    return this.request<ComputerControlState>(`/v1/computer-control/tasks/${runId}/cancel`, { method: 'POST' });
  }

  async emergencyStopComputerControl(): Promise<{ status: string }> {
    return this.request<{ status: string }>('/v1/computer-control/emergency-stop', { method: 'POST' });
  }

  // Conversations
  async getConversations(): Promise<ConversationResponse[]> {
    return this.request<ConversationResponse[]>('/v1/conversations');
  }

  async createConversation(title?: string): Promise<ConversationResponse> {
    return this.request<ConversationResponse>('/v1/conversations', {
      method: 'POST',
      body: JSON.stringify({ title: title || null }),
    });
  }

  async deleteConversation(conversationId: string): Promise<void> {
    return this.request<void>(`/v1/conversations/${conversationId}`, {
      method: 'DELETE',
    });
  }

  async getMessages(conversationId: string): Promise<MessageResponse[]> {
    return this.request<MessageResponse[]>(`/v1/conversations/${conversationId}/messages`);
  }

  // Tasks & Agent Engine
  async planTask(planRequest: AgentPlanRequest): Promise<AgentPlanResponse> {
    return this.request<AgentPlanResponse>('/v1/agent/plan', {
      method: 'POST',
      body: JSON.stringify(planRequest),
    });
  }

  async getTasks(): Promise<TaskResponse[]> {
    return this.request<TaskResponse[]>('/v1/tasks');
  }

  async getResumableTasks(): Promise<TaskResponse[]> {
    return this.request<TaskResponse[]>('/v1/tasks/resumable');
  }

  async getTask(taskId: string): Promise<TaskResponse> {
    return this.request<TaskResponse>(`/v1/tasks/${taskId}`);
  }

  async getTaskRuns(taskId: string): Promise<AgentRunRecordResponse[]> {
    return this.request<AgentRunRecordResponse[]>(`/v1/tasks/${taskId}/runs`);
  }

  async approveTask(taskId: string, approved: boolean, note?: string): Promise<TaskResponse> {
    return this.request<TaskResponse>(`/v1/tasks/${taskId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved, note: note || null }),
    });
  }

  async pauseTask(taskId: string): Promise<TaskResponse> {
    return this.request<TaskResponse>(`/v1/tasks/${taskId}/pause`, {
      method: 'POST',
    });
  }

  async resumeTask(taskId: string): Promise<TaskResponse> {
    return this.request<TaskResponse>(`/v1/tasks/${taskId}/resume`, {
      method: 'POST',
    });
  }

  async cancelTask(taskId: string): Promise<TaskResponse> {
    return this.request<TaskResponse>(`/v1/tasks/${taskId}/cancel`, {
      method: 'POST',
    });
  }

  async runTask(taskId: string): Promise<AgentRunResponse> {
    return this.request<AgentRunResponse>(`/v1/tasks/${taskId}/run`, {
      method: 'POST',
    });
  }

  async runTaskBackground(taskId: string): Promise<AgentRunResponse> {
    return this.request<AgentRunResponse>(`/v1/tasks/${taskId}/run/background`, {
      method: 'POST',
    });
  }

  // Memories
  async getMemories(category?: string): Promise<MemoryResponse[]> {
    const query = category ? `?category=${category}` : '';
    return this.request<MemoryResponse[]>(`/v1/memories${query}`);
  }

  async searchMemories(query: string): Promise<MemoryResponse[]> {
    return this.request<MemoryResponse[]>(`/v1/memories/search?q=${encodeURIComponent(query)}`);
  }

  async createMemory(req: MemoryCreateRequest): Promise<MemoryResponse> {
    return this.request<MemoryResponse>('/v1/memories', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async updateMemory(memoryId: number, req: MemoryUpdateRequest): Promise<MemoryResponse> {
    return this.request<MemoryResponse>(`/v1/memories/${memoryId}`, {
      method: 'PATCH',
      body: JSON.stringify(req),
    });
  }

  async deleteMemory(memoryId: number): Promise<void> {
    return this.request<void>(`/v1/memories/${memoryId}`, {
      method: 'DELETE',
    });
  }

  // Web & Self-Improvement
  async getWebActions(): Promise<WebActionResponse[]> {
    return this.request<WebActionResponse[]>('/v1/web/actions');
  }

  async getChangeRequests(): Promise<ChangeRequestResponse[]> {
    return this.request<ChangeRequestResponse[]>('/v1/self-improvement/requests');
  }

  async createChangeRequest(req: ChangeRequestCreateRequest): Promise<ChangeRequestResponse> {
    return this.request<ChangeRequestResponse>('/v1/self-improvement/requests', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async decideChangeRequest(
    requestId: string,
    decision: ChangeRequestDecisionRequest
  ): Promise<ChangeRequestResponse> {
    return this.request<ChangeRequestResponse>(`/v1/self-improvement/requests/${requestId}/decide`, {
      method: 'POST',
      body: JSON.stringify(decision),
    });
  }

  async testChangeRequest(requestId: string): Promise<ChangeRequestResponse> {
    return this.request<ChangeRequestResponse>(`/v1/self-improvement/requests/${requestId}/test`, {
      method: 'POST',
    });
  }

  async applyChangeRequest(requestId: string): Promise<ChangeRequestResponse> {
    return this.request<ChangeRequestResponse>(`/v1/self-improvement/requests/${requestId}/apply`, {
      method: 'POST',
    });
  }

  async rollbackChangeRequest(requestId: string): Promise<ChangeRequestResponse> {
    return this.request<ChangeRequestResponse>(`/v1/self-improvement/requests/${requestId}/rollback`, {
      method: 'POST',
    });
  }

  // Model Selection
  async selectModel(model: string): Promise<{ current_model: string }> {
    return this.request<{ current_model: string }>('/v1/models/select', {
      method: 'POST',
      body: JSON.stringify({ model }),
    });
  }

  // Settings
  async getSettings(): Promise<SettingsResponse> {
    return this.request<SettingsResponse>('/v1/settings');
  }

  async updatePersonality(
    personality_mode: 'adaptive' | 'friendly' | 'professional'
  ): Promise<{ personality_mode: string }> {
    return this.request<{ personality_mode: string }>('/v1/settings/personality', {
      method: 'POST',
      body: JSON.stringify({ personality_mode }),
    });
  }

  // System Information
  async getSystemInfo(): Promise<SystemInfoResponse> {
    return this.request<SystemInfoResponse>('/v1/system/info');
  }

  // Audit Logs
  async getAuditEvents(
    category?: string,
    search?: string,
    limit: number = 100
  ): Promise<AuditItemResponse[]> {
    const params = new URLSearchParams();
    if (category && category !== 'all') params.set('category', category);
    if (search && search.trim()) params.set('search', search.trim());
    params.set('limit', String(limit));
    return this.request<AuditItemResponse[]>(`/v1/audit?${params.toString()}`);
  }
}

export const api = new ApiClient();
