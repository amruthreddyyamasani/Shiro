import React, { useState, useEffect, useCallback } from 'react';
import {
  Cpu,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  HardDrive,
  ShieldCheck,
  Check,
} from 'lucide-react';
import { api } from '../../api/client';
import { ModelRecommendationResponse, HealthResponse } from '../../api/types';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { formatBytes } from '../../lib/utils';

export const ModelsView: React.FC = () => {
  const [modelInfo, setModelInfo] = useState<ModelRecommendationResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [switchingModel, setSwitchingModel] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const loadModels = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [m, h] = await Promise.all([
        api.getModelRecommendations(),
        api.getHealth(),
      ]);
      setModelInfo(m);
      setHealth(h);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  const handleSelectModel = async (modelName: string) => {
    setSwitchingModel(modelName);
    setError(null);
    setSuccessMessage(null);
    try {
      const res = await api.selectModel(modelName);
      if (res.current_model === modelName) {
        setSuccessMessage(`Active inference model switched to ${modelName}.`);
        await loadModels();
        setTimeout(() => setSuccessMessage(null), 4000);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSwitchingModel(null);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-background p-6 space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between pb-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-blue/10 border border-accent-blue/30 flex items-center justify-center text-accent-blue">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold font-mono text-text-primary tracking-wide">
                LOCAL INFERENCE MODELS
              </h1>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-raised text-accent-cyan border border-border flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
                <span>OLLAMA LOCAL DAEMON</span>
              </span>
            </div>
            <p className="text-xs text-text-secondary">
              Inspect verified locally installed model weights. Switch active inference runtime on localhost.
            </p>
          </div>
        </div>

        <Button size="sm" variant="outline" onClick={loadModels} isLoading={isLoading}>
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

      {successMessage && (
        <div className="p-3 rounded bg-emerald-950/30 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Ollama Daemon Status Banner */}
      <div className="p-4 rounded-lg bg-surface border border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono">
        <div className="flex items-center gap-2.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          <span className="text-text-secondary">OLLAMA HOST:</span>
          <span className="text-text-primary font-bold">{health?.ollama_base_url || 'http://127.0.0.1:11434'}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-text-muted">ACTIVE MODEL:</span>
          <span className="px-2 py-0.5 rounded bg-accent-cyan/15 text-accent-cyan font-bold border border-accent-cyan/30">
            {health?.model || modelInfo?.current_model || 'shiro:latest'}
          </span>
        </div>
      </div>

      {/* Model Cards Grid */}
      <div className="space-y-3">
        <span className="text-xs font-mono font-bold text-text-muted uppercase tracking-wider">
          Installed Models ({modelInfo?.models.length || 0})
        </span>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {modelInfo?.models.map((m) => {
            const isActive = m.name === (health?.model || modelInfo.current_model);
            return (
              <Card
                key={m.name}
                className={`space-y-4 flex flex-col justify-between transition-colors ${
                  isActive ? 'border-accent-cyan bg-accent-cyan/[0.03]' : ''
                }`}
              >
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-mono text-sm font-bold text-text-primary break-all">
                      {m.name}
                    </span>
                    {isActive ? (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40 font-bold shrink-0">
                        ACTIVE
                      </span>
                    ) : m.recommended ? (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface-raised text-text-muted border border-border shrink-0">
                        RECOMMENDED
                      </span>
                    ) : null}
                  </div>

                  <div className="space-y-1 text-xs font-mono text-text-secondary">
                    <div className="flex items-center justify-between">
                      <span className="text-text-muted">Weight Size:</span>
                      <span className="text-text-primary">{formatBytes(m.size)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-text-muted">Status:</span>
                      <span className="text-emerald-400">Locally Installed</span>
                    </div>
                  </div>
                </div>

                <div className="pt-3 border-t border-border-subtle flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-[11px] font-mono text-text-muted">
                    <HardDrive className="w-3.5 h-3.5" />
                    <span>Air-Gapped</span>
                  </div>

                  {isActive ? (
                    <Button size="sm" variant="ghost" disabled>
                      <Check className="w-3.5 h-3.5 text-accent-cyan mr-1" />
                      <span>Active</span>
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => handleSelectModel(m.name)}
                      isLoading={switchingModel === m.name}
                    >
                      Activate
                    </Button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
};
