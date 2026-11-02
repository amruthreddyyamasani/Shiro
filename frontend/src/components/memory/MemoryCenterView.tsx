import React, { useState, useEffect } from 'react';
import { Brain, Search, Plus, Trash2, RefreshCw, AlertCircle, Sparkles } from 'lucide-react';
import { api } from '../../api/client';
import { MemoryResponse, MemoryCategory } from '../../api/types';
import { Button } from '../ui/Button';
import { formatDate } from '../../lib/utils';

export const MemoryCenterView: React.FC = () => {
  const [memories, setMemories] = useState<MemoryResponse[]>([]);
  const [category, setCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [showModal, setShowModal] = useState<boolean>(false);
  const [newContent, setNewContent] = useState<string>('');
  const [newCategory, setNewCategory] = useState<MemoryCategory>('general');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const loadMemories = async () => {
    setIsLoading(true);
    setError(null);
    try {
      if (searchQuery.trim()) {
        const results = await api.searchMemories(searchQuery.trim());
        setMemories(results);
      } else {
        const results = await api.getMemories(category === 'all' ? undefined : category);
        setMemories(results);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadMemories();
  }, [category, searchQuery]);

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    setIsSubmitting(true);
    try {
      await api.createMemory({ category: newCategory, content: newContent.trim() });
      setNewContent('');
      setShowModal(false);
      loadMemories();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this memory?')) return;
    try {
      await api.deleteMemory(id);
      loadMemories();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-background">
      {/* Top Header */}
      <div className="p-4 border-b border-border bg-sidebar/50 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-violet/10 border border-accent-violet/30 flex items-center justify-center text-accent-violet">
            <Brain className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold font-mono text-text-primary tracking-wide">
              MEMORY CENTER
            </h1>
            <p className="text-xs text-text-secondary">
              Inspect, manage, and edit long-term context automatically retrieved during chat conversations.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={loadMemories} isLoading={isLoading}>
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
          <Button size="sm" variant="primary" onClick={() => setShowModal(true)}>
            <Plus className="w-3.5 h-3.5" />
            <span>Add Memory</span>
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-3 mx-4 mt-3 rounded bg-red-950/30 border border-red-800 text-red-300 text-xs flex items-center gap-2 shrink-0">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Search and Category Filters */}
      <div className="p-4 border-b border-border flex flex-col sm:flex-row items-center justify-between gap-3 shrink-0 bg-surface/30">
        <div className="relative w-full sm:w-80">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search stored memories..."
            className="w-full pl-9 pr-3 py-1.5 rounded-md bg-surface border border-border text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-violet font-sans"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
          {['all', 'preferences', 'projects', 'skills', 'general'].map((cat) => (
            <button
              key={cat}
              onClick={() => {
                setSearchQuery('');
                setCategory(cat);
              }}
              className={`px-2.5 py-1 rounded text-xs font-mono uppercase tracking-wider transition-colors ${
                category === cat && !searchQuery
                  ? 'bg-accent-violet text-[#080b10] font-bold'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-raised'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Memory Grid */}
      <div className="flex-1 overflow-y-auto p-4">
        {memories.length === 0 ? (
          <div className="p-12 text-center rounded-xl border border-dashed border-border flex flex-col items-center justify-center space-y-3">
            <Sparkles className="w-8 h-8 text-text-muted" />
            <h3 className="text-sm font-semibold font-mono text-text-primary">NO MEMORIES SAVED</h3>
            <p className="text-xs text-text-muted max-w-sm">
              As you chat with SHIRO, facts, project context, and preferences are automatically extracted
              and stored locally. You can also add them manually.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {memories.map((m) => (
              <div
                key={m.id}
                className="p-4 rounded-lg bg-surface border border-border hover:border-border-hover transition-colors flex flex-col justify-between space-y-3"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-surface-raised text-accent-violet border border-border">
                      {m.category}
                    </span>
                    <span className="text-[10px] font-mono text-text-muted">
                      {formatDate(m.created_at)}
                    </span>
                  </div>
                  <p className="text-xs text-text-primary leading-relaxed">{m.content}</p>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-border-subtle text-xs">
                  <span className="text-[10px] font-mono text-text-muted">ID: {m.id}</span>
                  <button
                    onClick={() => handleDelete(m.id)}
                    className="p-1 text-text-muted hover:text-red-400 transition-colors"
                    title="Delete Memory"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Memory Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-surface-elevated border border-border rounded-xl p-5 space-y-4 shadow-2xl">
            <h3 className="text-sm font-bold font-mono uppercase tracking-wider text-text-primary">
              Add New Memory Record
            </h3>

            <div className="space-y-1">
              <label className="text-xs font-mono text-text-muted">Category</label>
              <select
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value as MemoryCategory)}
                className="w-full p-2 rounded bg-surface border border-border text-xs text-text-primary focus:outline-none focus:border-accent-violet"
              >
                <option value="preferences">Preferences</option>
                <option value="projects">Projects</option>
                <option value="skills">Skills</option>
                <option value="general">General</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-mono text-text-muted">Content</label>
              <textarea
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="e.g. Always write unit tests with pytest..."
                rows={4}
                className="w-full p-2.5 rounded bg-surface border border-border text-xs text-text-primary focus:outline-none focus:border-accent-violet resize-none"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button size="sm" variant="ghost" onClick={() => setShowModal(false)} disabled={isSubmitting}>
                Cancel
              </Button>
              <Button size="sm" variant="primary" onClick={handleCreate} isLoading={isSubmitting}>
                Save Memory
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
