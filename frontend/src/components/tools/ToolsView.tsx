import React, { useState, useEffect } from 'react';
import { Wrench, Shield, CheckCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import { ToolDefinitionResponse, CapabilityResponse } from '../../api/types';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';

export const ToolsView: React.FC = () => {
  const [tools, setTools] = useState<ToolDefinitionResponse[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [tList, cList] = await Promise.all([api.getTools(), api.getCapabilities()]);
      setTools(tList);
      setCapabilities(cList);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-background p-6 space-y-6">
      <div className="flex items-center justify-between pb-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-blue/10 border border-accent-blue/30 flex items-center justify-center text-accent-blue">
            <Wrench className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold font-mono text-text-primary tracking-wide">
              TOOL REGISTRY & CAPABILITIES
            </h1>
            <p className="text-xs text-text-secondary">
              Deterministic, registered local tools and execution boundaries enforcing strict isolation.
            </p>
          </div>
        </div>

        <Button size="sm" variant="outline" onClick={loadData} isLoading={isLoading}>
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </Button>
      </div>

      {/* Safety Policy Notice */}
      <div className="p-4 rounded-lg bg-surface border border-border flex items-start gap-3">
        <Shield className="w-5 h-5 text-accent-cyan shrink-0 mt-0.5" />
        <div className="space-y-1 text-xs">
          <div className="font-mono font-bold text-text-primary">LOCAL EXECUTION POLICY</div>
          <p className="text-text-secondary leading-relaxed">
            All tools run exclusively on localhost within configured workspace directories. Dangerous side
            effects (writing files, creating directories, external search) strictly require explicit one-time
            approval tokens. Arbitrary shell or PowerShell execution is strictly prohibited.
          </p>
        </div>
      </div>

      {/* Tools List */}
      <div className="space-y-3">
        <span className="text-xs font-mono font-bold text-text-muted uppercase tracking-wider">
          Registered Tool Handlers ({tools.length})
        </span>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {tools.map((tool) => (
            <Card key={tool.name} className="space-y-3 flex flex-col justify-between">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm font-bold text-accent-cyan">{tool.name}</span>
                  {tool.requires_approval ? (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      <span>Approval Required</span>
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                      <CheckCircle className="w-3 h-3" />
                      <span>Auto Permitted</span>
                    </span>
                  )}
                </div>
                <p className="text-xs text-text-secondary leading-relaxed">{tool.description}</p>
              </div>

              <div className="pt-2 border-t border-border-subtle flex items-center justify-between text-[11px] font-mono text-text-muted">
                <span>Scope: Approved Roots</span>
                <span>Type: Python AST/Validated</span>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* Capabilities Overview */}
      <div className="space-y-3 pt-4 border-t border-border">
        <span className="text-xs font-mono font-bold text-text-muted uppercase tracking-wider">
          System Capability Flags
        </span>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {capabilities.map((c) => (
            <div
              key={c.name}
              className="p-3 rounded-lg bg-surface border border-border space-y-1 text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono font-semibold text-text-primary">{c.name}</span>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                    c.execution_enabled
                      ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800'
                      : 'bg-surface-raised text-text-muted border-border'
                  }`}
                >
                  {c.status}
                </span>
              </div>
              <p className="text-[11px] text-text-secondary leading-tight">{c.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
