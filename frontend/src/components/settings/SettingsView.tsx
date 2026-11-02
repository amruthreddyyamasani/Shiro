import React, { useState, useEffect, useCallback } from 'react';
import {
  Settings as SettingsIcon,
  Shield,
  HardDrive,
  Cpu,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Sparkles,
  Lock,
} from 'lucide-react';
import { api } from '../../api/client';
import {
  HealthResponse,
  ModelRecommendationResponse,
  SettingsResponse,
} from '../../api/types';
import { Card, CardHeader, CardTitle } from '../ui/Card';
import { Button } from '../ui/Button';

export const SettingsView: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelRecommendationResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [selectedPersonality, setSelectedPersonality] = useState<
    'adaptive' | 'friendly' | 'professional'
  >('adaptive');
  const [selectedModel, setSelectedModel] = useState<string>('shiro:latest');
  const [personalitySaving, setPersonalitySaving] = useState<boolean>(false);
  const [personalitySavedMessage, setPersonalitySavedMessage] = useState<string | null>(null);
  const [modelSaving, setModelSaving] = useState<boolean>(false);
  const [modelSavedMessage, setModelSavedMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [h, m, s] = await Promise.all([
        api.getHealth(),
        api.getModelRecommendations(),
        api.getSettings(),
      ]);
      setHealth(h);
      setModelInfo(m);
      setSettings(s);
      setSelectedPersonality(s.personality_mode);
      setSelectedModel(s.ollama_model);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSavePersonality = async () => {
    setPersonalitySaving(true);
    setPersonalitySavedMessage(null);
    setError(null);
    try {
      const res = await api.updatePersonality(selectedPersonality);
      if (res.personality_mode === selectedPersonality) {
        setPersonalitySavedMessage(`Personality successfully updated to "${selectedPersonality}".`);
        setTimeout(() => setPersonalitySavedMessage(null), 4000);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPersonalitySaving(false);
    }
  };

  const handleSaveModel = async () => {
    setModelSaving(true);
    setModelSavedMessage(null);
    setError(null);
    try {
      const res = await api.selectModel(selectedModel);
      if (res.current_model === selectedModel) {
        setModelSavedMessage(`Active model successfully switched to "${selectedModel}".`);
        setTimeout(() => setModelSavedMessage(null), 4000);
        loadData();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setModelSaving(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-background p-6 space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between pb-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-surface-raised border border-border flex items-center justify-center text-text-primary">
            <SettingsIcon className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold font-mono text-text-primary tracking-wide">
              APPLICATION & SAFETY SETTINGS
            </h1>
            <p className="text-xs text-text-secondary">
              Configure runtime personality and model selection. Safety boundaries and local storage are immutable.
            </p>
          </div>
        </div>

        <Button size="sm" variant="outline" onClick={loadData} isLoading={isLoading}>
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-5xl">
        {/* Configurable: Personality Mode */}
        <Card className="space-y-4 border-l-4 border-l-accent-cyan">
          <CardHeader>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <CardTitle>Assistant Personality Mode</CardTitle>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30">
                  CONFIGURABLE
                </span>
              </div>
              <p className="text-xs text-text-secondary">
                Selects the system prompt injected into each conversation turn.
              </p>
            </div>
            <Sparkles className="w-4 h-4 text-accent-cyan" />
          </CardHeader>

          <div className="space-y-3">
            {[
              {
                id: 'adaptive' as const,
                title: 'Adaptive',
                desc: 'Dynamically adjusts explanation depth and structure to user prompts.',
              },
              {
                id: 'friendly' as const,
                title: 'Friendly',
                desc: 'Warm and encouraging companion; clear, respectful explanations.',
              },
              {
                id: 'professional' as const,
                title: 'Professional',
                desc: 'Methodical and precise; stateful planning and structured markdown.',
              },
            ].map((mode) => (
              <label
                key={mode.id}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedPersonality === mode.id
                    ? 'bg-surface-raised border-accent-cyan text-text-primary'
                    : 'bg-surface border-border text-text-secondary hover:border-border-subtle'
                }`}
              >
                <input
                  type="radio"
                  name="personality"
                  value={mode.id}
                  checked={selectedPersonality === mode.id}
                  onChange={() => setSelectedPersonality(mode.id)}
                  className="mt-1 text-accent-cyan focus:ring-0"
                />
                <div className="space-y-0.5">
                  <div className="font-mono text-xs font-bold text-text-primary">{mode.title}</div>
                  <div className="text-[11px] text-text-secondary">{mode.desc}</div>
                </div>
              </label>
            ))}

            <div className="flex items-center justify-between pt-2">
              <Button
                size="sm"
                variant="primary"
                onClick={handleSavePersonality}
                isLoading={personalitySaving}
                disabled={selectedPersonality === settings?.personality_mode && !personalitySavedMessage}
              >
                Save Personality
              </Button>

              {personalitySavedMessage && (
                <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{personalitySavedMessage}</span>
                </span>
              )}
            </div>
          </div>
        </Card>

        {/* Configurable: Active Ollama Model */}
        <Card className="space-y-4 border-l-4 border-l-accent-blue">
          <CardHeader>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <CardTitle>Active Inference Model</CardTitle>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-accent-blue/15 text-accent-blue border border-accent-blue/30">
                  CONFIGURABLE
                </span>
              </div>
              <p className="text-xs text-text-secondary">
                Switch active Ollama model from verified locally installed models.
              </p>
            </div>
            <Cpu className="w-4 h-4 text-accent-blue" />
          </CardHeader>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="block text-xs font-mono text-text-secondary">
                SELECT INSTALLED MODEL:
              </label>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full p-2 rounded bg-surface-raised border border-border text-xs font-mono text-text-primary focus:outline-none focus:border-accent-blue"
              >
                {modelInfo?.models.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name} {m.recommended ? '(Recommended)' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="p-2.5 rounded bg-surface border border-border text-xs font-mono text-text-secondary space-y-1">
              <div className="flex justify-between">
                <span>Current Active:</span>
                <span className="text-accent-cyan font-bold">{health?.model}</span>
              </div>
              <div className="flex justify-between">
                <span>Ollama Endpoint:</span>
                <span>{health?.ollama_base_url}</span>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <Button
                size="sm"
                variant="primary"
                onClick={handleSaveModel}
                isLoading={modelSaving}
                disabled={selectedModel === health?.model && !modelSavedMessage}
              >
                Switch Model
              </Button>

              {modelSavedMessage && (
                <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{modelSavedMessage}</span>
                </span>
              )}
            </div>
          </div>
        </Card>

        {/* Immutable: Security Boundaries */}
        <Card className="space-y-3">
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle>Security Boundaries</CardTitle>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-surface-raised text-text-muted border border-border flex items-center gap-1">
                <Lock className="w-2.5 h-2.5" />
                <span>IMMUTABLE SAFETY</span>
              </span>
            </div>
            <Shield className="w-4 h-4 text-emerald-400" />
          </CardHeader>
          <div className="space-y-2 text-xs">
            <div className="flex items-center gap-2 text-emerald-400">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>Cloud AI disabled: 100% air-gapped local inference</span>
            </div>
            <div className="flex items-center gap-2 text-emerald-400">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>Localhost network binding only (127.0.0.1)</span>
            </div>
            <div className="flex items-center gap-2 text-emerald-400">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>Thinking explicitly disabled for predictable local latency</span>
            </div>
            <div className="flex items-center gap-2 text-emerald-400">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>Tool operations require explicit one-time tokens</span>
            </div>
          </div>
        </Card>

        {/* Immutable: Persistence Store */}
        <Card className="space-y-3">
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle>Persistence & Storage</CardTitle>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-surface-raised text-text-muted border border-border flex items-center gap-1">
                <Lock className="w-2.5 h-2.5" />
                <span>READ-ONLY</span>
              </span>
            </div>
            <HardDrive className="w-4 h-4 text-accent-cyan" />
          </CardHeader>
          <div className="space-y-2 text-xs font-mono">
            <div className="space-y-1">
              <span className="text-text-muted">SQLite Storage Location:</span>
              <div className="p-2 rounded bg-surface-raised border border-border text-text-primary break-all text-[11px]">
                {settings?.database_path || '%LOCALAPPDATA%\\SHIRO\\data\\shiro.db'}
              </div>
            </div>
            <div className="flex justify-between items-center text-text-secondary pt-2 border-t border-border-subtle">
              <span>Write-Ahead Log:</span>
              <span className="text-emerald-400 font-bold">WAL Mode Active</span>
            </div>
            <div className="flex justify-between items-center text-text-secondary">
              <span>Max History Messages:</span>
              <span className="text-text-primary">{settings?.max_history_messages || 24}</span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
