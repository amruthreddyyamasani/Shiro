import React, { useState, useEffect, useCallback } from 'react';
import {
  GitPullRequest,
  Check,
  X,
  Play,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
  FileCode,
  ShieldAlert,
  RefreshCw,
  Plus,
  Terminal,
} from 'lucide-react';
import { api } from '../../api/client';
import { ChangeRequestResponse } from '../../api/types';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { formatDate } from '../../lib/utils';

export const SelfImprovementView: React.FC = () => {
  const [requests, setRequests] = useState<ChangeRequestResponse[]>([]);
  const [selectedRequest, setSelectedRequest] = useState<ChangeRequestResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // New Proposal Modal
  const [showModal, setShowModal] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [filePath, setFilePath] = useState<string>('config.example.json');
  const [fileContent, setFileContent] = useState<string>('');
  const [testCommand, setTestCommand] = useState<string>('pytest -q tests/test_config.py');

  const loadRequests = useCallback(async () => {
    setIsLoading(true);
    setActionError(null);
    try {
      const data = await api.getChangeRequests();
      setRequests(data);
      if (selectedRequest) {
        const refreshed = data.find((r) => r.id === selectedRequest.id);
        if (refreshed) setSelectedRequest(refreshed);
      } else if (data.length > 0) {
        setSelectedRequest(data[0]);
      }
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, [selectedRequest]);

  useEffect(() => {
    loadRequests();
  }, []);

  const handleDecide = async (id: string, approved: boolean) => {
    const actionName = approved ? 'Approve' : 'Reject';
    if (!confirm(`Are you sure you want to ${actionName} this proposal?`)) return;
    setActionLoading(`decide-${id}`);
    setActionError(null);
    try {
      const updated = await api.decideChangeRequest(id, { approved });
      setSelectedRequest(updated);
      await loadRequests();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(null);
    }
  };

  const handleRunTest = async (id: string) => {
    setActionLoading(`test-${id}`);
    setActionError(null);
    try {
      const updated = await api.testChangeRequest(id);
      setSelectedRequest(updated);
      await loadRequests();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(null);
    }
  };

  const handleApply = async (id: string) => {
    if (!confirm('Apply this approved change to the repository? A safety rollback snapshot will be created automatically.')) {
      return;
    }
    setActionLoading(`apply-${id}`);
    setActionError(null);
    try {
      const updated = await api.applyChangeRequest(id);
      setSelectedRequest(updated);
      await loadRequests();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(null);
    }
  };

  const handleRollback = async (id: string) => {
    if (!confirm('Revert applied changes back to pre-applied state from backup snapshot?')) {
      return;
    }
    setActionLoading(`rollback-${id}`);
    setActionError(null);
    try {
      const updated = await api.rollbackChangeRequest(id);
      setSelectedRequest(updated);
      await loadRequests();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(null);
    }
  };

  const handleCreateProposal = async () => {
    if (!title.trim() || !description.trim() || !filePath.trim()) return;
    setActionLoading('create');
    setActionError(null);
    try {
      const created = await api.createChangeRequest({
        title: title.trim(),
        description: description.trim(),
        files: [filePath.trim()],
        test_command: testCommand.trim() || 'pytest -q',
        proposed_files: { [filePath.trim()]: fileContent },
      });
      setShowModal(false);
      setTitle('');
      setDescription('');
      setFileContent('');
      await loadRequests();
      setSelectedRequest(created);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3" />
            <span>APPROVED</span>
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <XCircle className="w-3 h-3" />
            <span>REJECTED</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30">
            <Clock className="w-3 h-3" />
            <span>PROPOSED</span>
          </span>
        );
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-background">
      {/* Top Header */}
      <div className="p-4 border-b border-border bg-sidebar/50 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-violet/10 border border-accent-violet/30 flex items-center justify-center text-accent-violet">
            <GitPullRequest className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold font-mono text-text-primary tracking-wide">
                SELF-IMPROVEMENT & CODE REVIEW
              </h1>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-raised text-accent-violet border border-border">
                HUMAN-IN-THE-LOOP
              </span>
            </div>
            <p className="text-xs text-text-secondary">
              Inspect staged codebase diffs, run isolated test harnesses, and review explicit change applications.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={loadRequests} isLoading={isLoading}>
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
          <Button size="sm" variant="primary" onClick={() => setShowModal(true)}>
            <Plus className="w-3.5 h-3.5" />
            <span>Stage Proposal</span>
          </Button>
        </div>
      </div>

      {actionError && (
        <div className="p-3 mx-4 mt-3 rounded bg-red-950/30 border border-red-800 text-red-300 text-xs flex items-center gap-2 shrink-0">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Main Split Layout */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Proposals List (Left) */}
        <div className="w-80 md:w-96 border-r border-border overflow-y-auto p-4 space-y-3 shrink-0">
          <div className="flex items-center justify-between text-xs font-mono font-bold text-text-muted uppercase tracking-wider mb-1">
            <span>Change Proposals</span>
            <span>({requests.length})</span>
          </div>

          {requests.length === 0 ? (
            <div className="p-8 text-center rounded-xl border border-dashed border-border flex flex-col items-center justify-center space-y-2">
              <FileCode className="w-6 h-6 text-text-muted" />
              <p className="text-xs text-text-muted">No self-improvement proposals staged.</p>
            </div>
          ) : (
            requests.map((req) => {
              const isSelected = selectedRequest?.id === req.id;
              return (
                <div
                  key={req.id}
                  onClick={() => setSelectedRequest(req)}
                  className={`p-3.5 rounded-lg border cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-surface-raised border-accent-violet text-text-primary shadow-sm'
                      : 'bg-surface border-border text-text-secondary hover:text-text-primary hover:border-border-subtle'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-mono text-xs text-text-muted">
                      ID: {req.id.slice(0, 8)}...
                    </span>
                    {getStatusBadge(req.status)}
                  </div>
                  <h3 className="font-semibold text-xs text-text-primary truncate mb-1">
                    {req.title}
                  </h3>
                  <p className="text-[11px] text-text-muted line-clamp-2 mb-2 leading-relaxed">
                    {req.description}
                  </p>
                  <div className="flex items-center justify-between text-[10px] font-mono text-text-muted pt-2 border-t border-border-subtle">
                    <span>{req.files.length} file(s) affected</span>
                    <span>{formatDate(req.created_at)}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Selected Proposal Detail & Diff View (Right) */}
        <div className="flex-1 flex flex-col min-w-0 overflow-y-auto p-6 space-y-6">
          {selectedRequest ? (
            <div className="space-y-6 max-w-4xl">
              {/* Proposal Header & Actions */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold font-mono text-text-primary">
                      {selectedRequest.title}
                    </h2>
                    {getStatusBadge(selectedRequest.status)}
                    {selectedRequest.applied_at && (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">
                        APPLIED
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-text-secondary">{selectedRequest.description}</p>
                </div>

                {/* State Machine Actions */}
                <div className="flex items-center gap-2 flex-wrap">
                  {selectedRequest.status === 'proposed' && (
                    <>
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => handleDecide(selectedRequest.id, true)}
                        isLoading={actionLoading === `decide-${selectedRequest.id}`}
                      >
                        <Check className="w-3.5 h-3.5" />
                        <span>Approve Proposal</span>
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => handleDecide(selectedRequest.id, false)}
                        isLoading={actionLoading === `decide-${selectedRequest.id}`}
                      >
                        <X className="w-3.5 h-3.5" />
                        <span>Reject</span>
                      </Button>
                    </>
                  )}

                  {selectedRequest.status === 'approved' && !selectedRequest.applied_at && (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleRunTest(selectedRequest.id)}
                        isLoading={actionLoading === `test-${selectedRequest.id}`}
                      >
                        <Play className="w-3.5 h-3.5" />
                        <span>Run Staging Tests</span>
                      </Button>

                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => handleApply(selectedRequest.id)}
                        isLoading={actionLoading === `apply-${selectedRequest.id}`}
                      >
                        <span>Apply Changes</span>
                      </Button>
                    </>
                  )}

                  {selectedRequest.applied_at && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleRollback(selectedRequest.id)}
                      isLoading={actionLoading === `rollback-${selectedRequest.id}`}
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Roll Back</span>
                    </Button>
                  )}
                </div>
              </div>

              {/* Safety Policy Banner */}
              <div className="p-3.5 rounded-lg bg-surface border border-border flex items-start gap-3 text-xs">
                <ShieldAlert className="w-4 h-4 text-accent-violet shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <span className="font-mono font-bold text-text-primary">
                    AUTOMATIC ROLLBACK & BACKUP ENFORCED
                  </span>
                  <p className="text-text-secondary leading-relaxed">
                    Code modifications are staged in an isolated temporary tree. Tests execute in sandbox
                    before applying. Changes to production workspace retain atomic snapshots for immediate rollback.
                  </p>
                </div>
              </div>

              {/* Test Harness Status Card */}
              <Card className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-accent-cyan" />
                    <span className="text-xs font-mono font-bold text-text-primary">
                      STAGING TEST HARNESS
                    </span>
                  </div>
                  <span
                    className={`text-[11px] font-mono px-2 py-0.5 rounded border ${
                      selectedRequest.test_status === 'passed'
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        : selectedRequest.test_status === 'failed'
                        ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                        : 'bg-surface-raised text-text-muted border-border'
                    }`}
                  >
                    {selectedRequest.test_status.toUpperCase()}
                  </span>
                </div>

                <div className="text-xs font-mono text-text-secondary">
                  Command: <code className="text-accent-cyan">{selectedRequest.test_command}</code>
                </div>

                {selectedRequest.test_output && (
                  <pre className="p-3 rounded bg-[#05070a] border border-border text-[11px] font-mono text-text-secondary overflow-x-auto whitespace-pre-wrap max-h-48 leading-relaxed">
                    {selectedRequest.test_output}
                  </pre>
                )}
              </Card>

              {/* File-Level Staged Diffs */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-text-primary uppercase tracking-wider flex items-center gap-2">
                    <FileCode className="w-4 h-4 text-accent-violet" />
                    <span>Staged Unified Diff</span>
                  </span>
                  <span className="text-xs font-mono text-text-muted">
                    Files: {selectedRequest.files.join(', ')}
                  </span>
                </div>

                <div className="rounded-lg border border-border bg-[#05070a] p-4 overflow-x-auto font-mono text-xs leading-relaxed max-h-96">
                  {selectedRequest.diff ? (
                    selectedRequest.diff.split('\n').map((line, idx) => {
                      let colorClass = 'text-text-secondary';
                      if (line.startsWith('+') && !line.startsWith('+++')) {
                        colorClass = 'text-emerald-400 bg-emerald-950/20';
                      } else if (line.startsWith('-') && !line.startsWith('---')) {
                        colorClass = 'text-rose-400 bg-rose-950/20';
                      } else if (line.startsWith('@@')) {
                        colorClass = 'text-accent-cyan';
                      }
                      return (
                        <div key={idx} className={`${colorClass} px-1.5 py-0.5 rounded-sm`}>
                          {line}
                        </div>
                      );
                    })
                  ) : (
                    <span className="text-text-muted italic">No diff detected in staging.</span>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-2">
              <GitPullRequest className="w-10 h-10 text-text-muted opacity-40" />
              <h3 className="text-sm font-semibold font-mono text-text-primary">
                NO PROPOSAL SELECTED
              </h3>
              <p className="text-xs text-text-muted">
                Select a change proposal from the list on the left to inspect its diff and test results.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Stage New Proposal Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-surface border border-border rounded-xl w-full max-w-lg p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between pb-2 border-b border-border">
              <h3 className="font-mono font-bold text-sm text-text-primary">
                STAGE CODE CHANGE PROPOSAL
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className="text-text-muted hover:text-text-primary p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-mono text-text-secondary mb-1">PROPOSAL TITLE</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Optimize cache timeout configuration"
                  className="w-full p-2 rounded bg-surface-raised border border-border text-text-primary focus:outline-none focus:border-accent-violet font-sans"
                />
              </div>

              <div>
                <label className="block font-mono text-text-secondary mb-1">DESCRIPTION</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Explain the proposed architectural or operational change..."
                  rows={2}
                  className="w-full p-2 rounded bg-surface-raised border border-border text-text-primary focus:outline-none focus:border-accent-violet font-sans resize-none"
                />
              </div>

              <div>
                <label className="block font-mono text-text-secondary mb-1">TARGET RELATIVE FILE</label>
                <input
                  type="text"
                  value={filePath}
                  onChange={(e) => setFilePath(e.target.value)}
                  placeholder="config.example.json"
                  className="w-full p-2 rounded bg-surface-raised border border-border text-text-primary focus:outline-none focus:border-accent-violet font-mono"
                />
              </div>

              <div>
                <label className="block font-mono text-text-secondary mb-1">TEST COMMAND</label>
                <input
                  type="text"
                  value={testCommand}
                  onChange={(e) => setTestCommand(e.target.value)}
                  placeholder="pytest -q tests/test_config.py"
                  className="w-full p-2 rounded bg-surface-raised border border-border text-text-primary focus:outline-none focus:border-accent-violet font-mono"
                />
              </div>

              <div>
                <label className="block font-mono text-text-secondary mb-1">PROPOSED FILE CONTENT</label>
                <textarea
                  value={fileContent}
                  onChange={(e) => setFileContent(e.target.value)}
                  placeholder="Enter full UTF-8 contents of proposed file..."
                  rows={4}
                  className="w-full p-2 rounded bg-[#05070a] border border-border text-accent-cyan focus:outline-none focus:border-accent-violet font-mono resize-none text-[11px]"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-border">
              <Button size="sm" variant="ghost" onClick={() => setShowModal(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                variant="primary"
                onClick={handleCreateProposal}
                isLoading={actionLoading === 'create'}
              >
                Submit Proposal
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
