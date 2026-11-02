import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Sidebar, NavTab } from '../components/layout/Sidebar';
import { ContextPanel } from '../components/layout/ContextPanel';
import { DashboardView } from '../components/dashboard/DashboardView';
import { ChatView } from '../components/chat/ChatView';
import { TaskManagerView } from '../components/agent/TaskManagerView';
import { ApprovalCenterView } from '../components/agent/ApprovalCenterView';
import { MemoryCenterView } from '../components/memory/MemoryCenterView';
import { ToolsView } from '../components/tools/ToolsView';
import { ModelsView } from '../components/models/ModelsView';
import { SettingsView } from '../components/settings/SettingsView';
import { ActivityLogView } from '../components/audit/ActivityLogView';
import { SelfImprovementView } from '../components/improvement/SelfImprovementView';
import { SystemInfoView } from '../components/system/SystemInfoView';
import { ComputerControlView } from '../components/computer/ComputerControlView';
import { EchoCompanion } from '../components/echo/EchoCompanion';
import { useEchoState } from '../components/echo/useEchoState';
import { api } from '../api/client';
import { ComputerControlState, HealthResponse, ToolApprovalResponse, TaskResponse, ConversationResponse } from '../api/types';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');
  // Collapse sidebar by default on small screens (< 768px)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(
    typeof window !== 'undefined' && window.innerWidth < 768
  );
  const [isContextPanelOpen, setIsContextPanelOpen] = useState<boolean>(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<ToolApprovalResponse[]>([]);
  const [activeTask, setActiveTask] = useState<TaskResponse | null>(null);
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [isChatStreaming, setIsChatStreaming] = useState<boolean>(false);
  const [computerControlState, setComputerControlState] = useState<ComputerControlState | null>(null);
  const globalFetchSequence = useRef(0);

  const fetchGlobalState = useCallback(async () => {
    const requestSequence = ++globalFetchSequence.current;
    try {
      const [h, apps, resumable, convs, allTasks] = await Promise.all([
        api.getHealth(),
        api.getToolApprovals('pending').catch(() => []),
        api.getResumableTasks().catch(() => []),
        api.getConversations().catch(() => []),
        api.getTasks().catch(() => []),
      ]);
      if (requestSequence !== globalFetchSequence.current) return;
      setHealth(h);
      setPendingApprovals(apps);
      setConversations(convs);
      setTasks(allTasks);
      setIsOnline(true);
      if (resumable.length > 0) {
        setActiveTask(resumable[0]);
      } else {
        setActiveTask(null);
      }
    } catch {
      if (requestSequence !== globalFetchSequence.current) return;
      setIsOnline(false);
    }
  }, []);

  useEffect(() => {
    fetchGlobalState();
    const interval = setInterval(fetchGlobalState, 5000);
    return () => clearInterval(interval);
  }, [fetchGlobalState]);

  // Keyboard shortcut Ctrl+B for Context Panel
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        setIsContextPanelOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleDecideApproval = async (approvalId: string, approved: boolean) => {
    try {
      await api.decideToolApproval(approvalId, approved);
      fetchGlobalState();
    } catch (err) {
      console.error(err);
    }
  };

  const handleSelectConversation = (cid: string) => {
    setActiveConversationId(cid);
    setActiveTab('chat');
  };

  const handleNewChat = () => {
    setActiveConversationId(null);
    setActiveTab('chat');
  };

  const echoState = useEchoState({
    activeTab,
    isOnline,
    isChatStreaming,
    tasks,
    pendingApprovals,
    computerControlState,
  });

  const handleDeleteConversation = async (cid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this conversation?')) return;
    try {
      await api.deleteConversation(cid);
      if (activeConversationId === cid) {
        setActiveConversationId(null);
      }
      fetchGlobalState();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-text-primary antialiased font-sans">
      {/* Collapsible Left Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        onNewChat={handleNewChat}
        pendingApprovalsCount={pendingApprovals.length}
        activeModel={health?.model || 'shiro:latest'}
        isOnline={isOnline}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
      />

      {/* Center Viewport */}
      <main className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        {activeTab === 'dashboard' && (
          <DashboardView onNavigate={setActiveTab} onNewChat={handleNewChat} />
        )}
        {activeTab === 'chat' && (
          <ChatView
            activeModel={health?.model || 'shiro:latest'}
            isOnline={isOnline}
            onToggleContextPanel={() => setIsContextPanelOpen(!isContextPanelOpen)}
            isContextPanelOpen={isContextPanelOpen}
            activeConversationId={activeConversationId}
            onSelectConversation={setActiveConversationId}
            onRefreshConversations={fetchGlobalState}
            onStreamingChange={setIsChatStreaming}
          />
        )}
        {activeTab === 'tasks' && <TaskManagerView />}
        {activeTab === 'computer-control' && <ComputerControlView onStateChange={setComputerControlState} />}
        {activeTab === 'approvals' && <ApprovalCenterView />}
        {activeTab === 'activity' && <ActivityLogView />}
        {activeTab === 'improvement' && <SelfImprovementView />}
        {activeTab === 'memory' && <MemoryCenterView />}
        {activeTab === 'tools' && <ToolsView />}
        {activeTab === 'models' && <ModelsView />}
        {activeTab === 'system' && <SystemInfoView />}
        {activeTab === 'settings' && <SettingsView />}
      </main>

      <EchoCompanion
        state={echoState}
        size="sm"
        className="fixed bottom-4 right-4"
      />

      {/* Contextual Right Drawer */}
      <ContextPanel
        isOpen={isContextPanelOpen}
        onClose={() => setIsContextPanelOpen(false)}
        activeTask={activeTask}
        pendingApprovals={pendingApprovals}
        onDecideApproval={handleDecideApproval}
        ollamaBaseUrl={health?.ollama_base_url || 'http://127.0.0.1:11434'}
        activeModel={health?.model || 'shiro:latest'}
      />
    </div>
  );
};
