import React, { useState } from 'react';
import {
  LayoutDashboard,
  MessageSquare,
  CheckSquare,
  ShieldAlert,
  Brain,
  Wrench,
  Settings,
  Plus,
  ShieldCheck,
  Cpu,
  Trash2,
  ChevronLeft,
  ChevronRight,
  MessageCircle,
  Activity,
  GitPullRequest,
  Server,
  Search,
  Crosshair,
} from 'lucide-react';
import { cn, formatDate } from '../../lib/utils';
import { StatusMark } from '../ui/StatusMark';
import { ConversationResponse } from '../../api/types';

export type NavTab =
  | 'dashboard'
  | 'chat'
  | 'tasks'
  | 'computer-control'
  | 'approvals'
  | 'activity'
  | 'improvement'
  | 'memory'
  | 'tools'
  | 'models'
  | 'system'
  | 'settings';

interface SidebarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  onNewChat: () => void;
  pendingApprovalsCount: number;
  activeModel: string;
  isOnline: boolean;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  conversations: ConversationResponse[];
  activeConversationId?: string | null;
  onSelectConversation: (cid: string) => void;
  onDeleteConversation: (cid: string, e: React.MouseEvent) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  onNewChat,
  pendingApprovalsCount,
  activeModel,
  isOnline,
  isCollapsed,
  onToggleCollapse,
  conversations,
  activeConversationId,
  onSelectConversation,
  onDeleteConversation,
}) => {
  const [convSearch, setConvSearch] = useState<string>('');

  const navItems = [
    { id: 'dashboard' as NavTab, label: 'Dashboard', icon: LayoutDashboard },
    { id: 'chat' as NavTab, label: 'Chat', icon: MessageSquare },
    { id: 'tasks' as NavTab, label: 'Task Manager', icon: CheckSquare },
    { id: 'computer-control' as NavTab, label: 'Computer Control', icon: Crosshair },
    {
      id: 'approvals' as NavTab,
      label: 'Approvals',
      icon: ShieldAlert,
      badge: pendingApprovalsCount > 0 ? pendingApprovalsCount : undefined,
    },
    { id: 'activity' as NavTab, label: 'Activity Log', icon: Activity },
    { id: 'improvement' as NavTab, label: 'Code Review', icon: GitPullRequest },
    { id: 'memory' as NavTab, label: 'Memory Center', icon: Brain },
    { id: 'tools' as NavTab, label: 'Tool Registry', icon: Wrench },
    { id: 'models' as NavTab, label: 'Models', icon: Cpu },
    { id: 'system' as NavTab, label: 'System Info', icon: Server },
    { id: 'settings' as NavTab, label: 'Settings', icon: Settings },
  ];

  return (
    <aside
      className={cn(
        'bg-sidebar border-r border-border flex flex-col justify-between h-screen select-none shrink-0 transition-all duration-200',
        isCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Top Header & Navigation */}
      <div className="flex flex-col flex-1 min-h-0">
        {/* Brand & Collapse Toggle */}
        <div className="p-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-8 h-8 rounded-md bg-accent-cyan/10 border border-accent-cyan/40 flex items-center justify-center text-accent-cyan font-mono font-bold text-sm shadow-sm shrink-0">
              S
            </div>
            {!isCollapsed && (
              <div className="truncate">
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-text-primary tracking-wider text-sm font-mono">
                    SHIRO
                  </span>
                  <span className="text-[10px] font-mono px-1 py-0.2 rounded bg-surface-raised text-text-muted border border-border">
                    v0.1
                  </span>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-text-muted">
                  <ShieldCheck className="w-3 h-3 text-emerald-400" />
                  <span>Local Only</span>
                </div>
              </div>
            )}
          </div>

          <button
            onClick={onToggleCollapse}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface-raised transition-colors shrink-0"
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* New Conversation Button */}
        <div className="p-2.5">
          <button
            onClick={onNewChat}
            className={cn(
              'flex items-center justify-center gap-2 rounded-md bg-accent-cyan text-[#080b10] hover:bg-accent-cyan/90 font-medium font-mono transition-colors shadow-sm',
              isCollapsed ? 'w-full py-2.5' : 'w-full py-2 px-3 text-xs'
            )}
            title="New Conversation"
          >
            <Plus className="w-4 h-4" />
            {!isCollapsed && <span>NEW CONVERSATION</span>}
          </button>
        </div>

        {/* Primary Navigation */}
        <nav className="px-2 py-1 space-y-0.5 shrink-0">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                title={isCollapsed ? item.label : undefined}
                className={cn(
                  'w-full flex items-center rounded-md text-xs font-medium transition-colors text-left',
                  isCollapsed ? 'justify-center p-2.5' : 'justify-between px-3 py-2',
                  isActive
                    ? 'bg-surface-raised text-accent-cyan font-semibold border-l-2 border-accent-cyan'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface'
                )}
              >
                <div className="flex items-center gap-2.5">
                  <Icon className={cn('w-4 h-4 shrink-0', isActive ? 'text-accent-cyan' : 'text-text-muted')} />
                  {!isCollapsed && <span>{item.label}</span>}
                </div>
                {!isCollapsed && item.badge !== undefined ? (
                  <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
                    {item.badge}
                  </span>
                ) : null}
              </button>
            );
          })}
        </nav>

        {/* Conversation History Section (visible when expanded) */}
        {!isCollapsed && (
          <div className="flex-1 flex flex-col min-h-0 mt-2 pt-2 border-t border-border px-2">
            <div className="px-2 pb-1.5 text-[11px] font-mono font-semibold uppercase text-text-muted tracking-wider flex items-center justify-between">
              <span>Conversations</span>
              <span className="text-[10px] text-text-muted">({conversations.length})</span>
            </div>

            {conversations.length > 3 && (
              <div className="relative px-1 mb-1.5">
                <Search className="w-3 h-3 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  type="text"
                  value={convSearch}
                  onChange={(e) => setConvSearch(e.target.value)}
                  placeholder="Filter threads..."
                  className="w-full pl-7 pr-2 py-1 rounded bg-surface border border-border text-[11px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-cyan"
                />
              </div>
            )}

            <div className="flex-1 overflow-y-auto space-y-0.5 pr-1">
              {conversations.length === 0 ? (
                <div className="text-[11px] text-text-muted text-center py-4 px-2 italic">
                  No saved conversations
                </div>
              ) : (
                conversations
                  .filter((conv) => !convSearch || conv.title?.toLowerCase().includes(convSearch.toLowerCase()))
                  .map((conv) => {
                    const isSelected = activeConversationId === conv.id;
                    return (
                      <div
                        key={conv.id}
                        onClick={() => onSelectConversation(conv.id)}
                        className={cn(
                          'group flex items-center justify-between px-2.5 py-2 rounded-md text-xs cursor-pointer transition-colors',
                          isSelected
                            ? 'bg-surface-raised text-accent-cyan border border-accent-cyan/30'
                            : 'text-text-secondary hover:text-text-primary hover:bg-surface'
                        )}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <MessageCircle className="w-3.5 h-3.5 shrink-0 opacity-60" />
                          <div className="truncate">
                            <div className="truncate font-medium">{conv.title || 'New conversation'}</div>
                            <div className="text-[10px] text-text-muted font-mono">
                              {formatDate(conv.updated_at)}
                            </div>
                          </div>
                        </div>

                        <button
                          onClick={(e) => onDeleteConversation(conv.id, e)}
                          className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-red-400 transition-opacity ml-1"
                          title="Delete conversation"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    );
                  })
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer System Status */}
      <div className="p-3 border-t border-border bg-surface/50 text-xs shrink-0">
        {isCollapsed ? (
          <div className="flex flex-col items-center gap-2">
            <span
              className={cn(
                'w-2 h-2 rounded-full',
                isOnline ? 'bg-emerald-400' : 'bg-rose-400'
              )}
              title={isOnline ? 'Backend Online' : 'Backend Offline'}
            />
            <div title={activeModel}>
              <Cpu className="w-4 h-4 text-accent-blue" />
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-text-muted text-[11px] font-mono">BACKEND</span>
              <StatusMark status={isOnline ? 'ok' : 'offline'} label={isOnline ? 'Online' : 'Offline'} />
            </div>
            <div className="flex items-center gap-2 p-1.5 rounded bg-surface-raised border border-border">
              <Cpu className="w-3.5 h-3.5 text-accent-blue shrink-0" />
              <div className="truncate">
                <div className="text-[10px] text-text-muted font-mono leading-none">ACTIVE MODEL</div>
                <div className="text-xs font-mono text-text-primary truncate">{activeModel}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
