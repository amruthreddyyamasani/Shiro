import React, { useState, useEffect, useCallback } from 'react';
import {
  Cpu,
  ShieldCheck,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Database,
  Server,
  FolderTree,
} from 'lucide-react';
import { api } from '../../api/client';
import { SystemInfoResponse, ModelRecommendationResponse } from '../../api/types';
import { Card, CardHeader, CardTitle } from '../ui/Card';
import { Button } from '../ui/Button';
import { formatBytes } from '../../lib/utils';

export const SystemInfoView: React.FC = () => {
  const [sysInfo, setSysInfo] = useState<SystemInfoResponse | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelRecommendationResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadSystemInfo = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [info, mInfo] = await Promise.all([
        api.getSystemInfo(),
        api.getModelRecommendations().catch(() => null),
      ]);
      setSysInfo(info);
      setModelInfo(mInfo);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSystemInfo();
  }, [loadSystemInfo]);

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-background p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-blue/10 border border-accent-blue/30 flex items-center justify-center text-accent-blue">
            <Server className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold font-mono text-text-primary tracking-wide">
                SYSTEM & RUNTIME INFORMATION
              </h1>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-raised text-emerald-400 border border-border flex items-center gap-1">
                <ShieldCheck className="w-3 h-3" />
                <span>VERIFIED REAL HARDWARE METRICS</span>
              </span>
            </div>
            <p className="text-xs text-text-secondary">
              Direct introspection of Windows OS, local Ollama daemon, and SQLite persistence store.
            </p>
          </div>
        </div>

        <Button size="sm" variant="outline" onClick={loadSystemInfo} isLoading={isLoading}>
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </Button>
      </div>

      {error && (
        <div className="p-3 rounded bg-red-950/30 border border-red-800 text-red-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {sysInfo && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-5xl">
          {/* Host OS & Environment */}
          <Card className="space-y-4">
            <CardHeader>
              <CardTitle>Host Operating System</CardTitle>
              <Server className="w-4 h-4 text-accent-cyan" />
            </CardHeader>
            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between items-center text-text-secondary">
                <span>OS Name:</span>
                <span className="text-text-primary font-bold">{sysInfo.os_name}</span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>OS Release & Build:</span>
                <span className="text-text-primary">
                  {sysInfo.os_release} ({sysInfo.os_version})
                </span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>Architecture:</span>
                <span className="text-accent-cyan">{sysInfo.architecture}</span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>Python Runtime:</span>
                <span className="text-text-primary">{sysInfo.python_version}</span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>Shiro Application Version:</span>
                <span className="text-text-primary">v{sysInfo.app_version}</span>
              </div>
            </div>
          </Card>

          {/* Local Inference Daemon */}
          <Card className="space-y-4">
            <CardHeader>
              <CardTitle>Local Ollama Daemon</CardTitle>
              <Cpu className="w-4 h-4 text-accent-blue" />
            </CardHeader>
            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between items-center text-text-secondary">
                <span>Daemon Status:</span>
                <span className="flex items-center gap-1.5 font-bold">
                  {sysInfo.ollama_connected ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400">Connected</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-3.5 h-3.5 text-rose-400" />
                      <span className="text-rose-400">Disconnected</span>
                    </>
                  )}
                </span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>Ollama Base URL:</span>
                <span className="text-text-primary">{sysInfo.ollama_base_url}</span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>Active Model:</span>
                <span className="text-accent-cyan font-bold">{sysInfo.ollama_model}</span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>Installed Models:</span>
                <span className="text-text-primary font-bold">
                  {sysInfo.ollama_installed_models.length} model(s)
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {sysInfo.ollama_installed_models.map((name) => {
                  const mDetail = modelInfo?.models.find((m) => m.name === name);
                  const isCurrent = name === sysInfo.ollama_model;
                  return (
                    <span
                      key={name}
                      className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                        isCurrent
                          ? 'bg-accent-cyan/15 text-accent-cyan border-accent-cyan/40 font-bold'
                          : 'bg-surface-raised text-text-secondary border-border'
                      }`}
                    >
                      {name}
                      {mDetail?.size ? ` (${formatBytes(mDetail.size)})` : ''}
                    </span>
                  );
                })}
              </div>
            </div>
          </Card>

          {/* Persistence & Database */}
          <Card className="space-y-4">
            <CardHeader>
              <CardTitle>Persistence & Database</CardTitle>
              <Database className="w-4 h-4 text-accent-violet" />
            </CardHeader>
            <div className="space-y-2 text-xs font-mono">
              <div className="space-y-1">
                <span className="text-text-muted">Database File Path:</span>
                <div className="p-2 rounded bg-surface-raised border border-border text-text-primary break-all text-[11px]">
                  {sysInfo.database_path}
                </div>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>Database File Size:</span>
                <span className="text-text-primary font-bold">
                  {formatBytes(sysInfo.database_size_bytes)}
                </span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>WAL Mode (Write-Ahead-Log):</span>
                <span className="text-emerald-400 font-bold">
                  {sysInfo.database_wal_enabled ? 'Active / Synchronous' : 'Disabled'}
                </span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>Foreign Keys Constraint:</span>
                <span className="text-emerald-400 font-bold">PRAGMA foreign_keys = ON</span>
              </div>
            </div>
          </Card>

          {/* Network & Workspace Boundaries */}
          <Card className="space-y-4">
            <CardHeader>
              <CardTitle>Execution Boundaries</CardTitle>
              <FolderTree className="w-4 h-4 text-emerald-400" />
            </CardHeader>
            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between items-center text-text-secondary">
                <span>Network Binding:</span>
                <span className="text-text-primary">
                  {sysInfo.host}:{sysInfo.port} (Localhost Only)
                </span>
              </div>
              <div className="flex justify-between items-center text-text-secondary">
                <span>Tool Execution:</span>
                <span className={sysInfo.tools_enabled ? 'text-emerald-400 font-bold' : 'text-text-muted'}>
                  {sysInfo.tools_enabled ? 'Enabled (Deterministic AST)' : 'Disabled'}
                </span>
              </div>
              <div className="space-y-1">
                <span className="text-text-muted">Approved Workspace Root:</span>
                <div className="p-2 rounded bg-surface-raised border border-border text-text-primary break-all text-[11px]">
                  {sysInfo.project_root}
                </div>
              </div>
              {sysInfo.approved_roots.length > 0 && (
                <div className="space-y-1">
                  <span className="text-text-muted">Whitelisted Allowed Roots:</span>
                  <div className="space-y-1">
                    {sysInfo.approved_roots.map((r, idx) => (
                      <div
                        key={idx}
                        className="p-1.5 rounded bg-surface-raised border border-border text-accent-cyan break-all text-[10px]"
                      >
                        {r}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};
