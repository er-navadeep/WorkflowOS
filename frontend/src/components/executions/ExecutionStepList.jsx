import React from 'react';
import { 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Loader2, 
  AlertTriangle,
  Mail,
  MessageSquare,
  Database,
  Globe,
  Terminal,
  ShieldCheck
} from 'lucide-react';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

function getAppIcon(application) {
  const normalized = (application || '').toLowerCase();
  switch (normalized) {
    case 'gmail':
      return { icon: Mail, color: 'text-red-400 bg-red-950/40 border-red-800/40' };
    case 'slack':
      return { icon: MessageSquare, color: 'text-emerald-400 bg-emerald-950/40 border-emerald-800/40' };
    case 'crm':
      return { icon: Database, color: 'text-blue-400 bg-blue-950/40 border-blue-800/40' };
    case 'browser':
      return { icon: Globe, color: 'text-cyan-400 bg-cyan-950/40 border-cyan-800/40' };
    default:
      return { icon: Terminal, color: 'text-slate-400 bg-slate-900 border-slate-700' };
  }
}

export function ExecutionStepList({ steps = [] }) {
  if (!steps || steps.length === 0) {
    return (
      <div className="p-4 rounded-xl bg-surface/40 border border-surface-border text-center text-xs text-slate-500 italic">
        No execution step records available.
      </div>
    );
  }

  // Sort by order 1..N
  const sortedSteps = [...steps].sort((a, b) => a.order - b.order);

  return (
    <div className="space-y-3">
      {sortedSteps.map((step) => {
        const appMeta = getAppIcon(step.application);
        const AppIcon = appMeta.icon;
        const isDryRun = step.status === 'dry_run';
        const isFailed = step.status === 'failed';
        const isRunning = step.status === 'running';

        return (
          <div 
            key={step.step_id || step.order}
            className={`p-4 rounded-2xl border transition-all ${
              isFailed 
                ? 'bg-rose-950/20 border-rose-800/50' 
                : isRunning
                  ? 'bg-blue-950/20 border-blue-800/50 shadow-md shadow-blue-950/20'
                  : 'bg-surface-elevated/40 border-surface-border/80 hover:border-surface-border'
            }`}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2 border-b border-surface-border/60">
              <div className="flex items-center gap-2.5">
                {/* Step Order Circle */}
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center font-mono font-bold text-xs shrink-0 ${
                  isFailed
                    ? 'bg-rose-900/40 text-rose-300 border border-rose-700/50'
                    : 'bg-surface border border-surface-border text-slate-300'
                }`}>
                  {step.order}
                </div>

                {/* Application Badge */}
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg text-xs font-mono font-semibold border ${appMeta.color}`}>
                  <AppIcon className="w-3.5 h-3.5" />
                  <span>{step.application}</span>
                </span>

                {/* Action Phrase */}
                <span className="text-xs font-mono text-slate-300 bg-surface px-2 py-0.5 rounded border border-surface-border">
                  {step.action}
                </span>

                {step.action === 'open_email' && (
                  <span className="text-2xs font-mono text-cyan-300 bg-cyan-950/40 border border-cyan-800/40 px-2 py-0.5 rounded">
                    Internal detail of Action 1
                  </span>
                )}
                {step.action === 'read_email' && (
                  <span className="text-2xs font-mono text-slate-400 bg-surface px-2 py-0.5 rounded">
                    Action 1: Read Email
                  </span>
                )}
                {step.action === 'download_file' && (
                  <span className="text-2xs font-mono text-slate-400 bg-surface px-2 py-0.5 rounded">
                    Action 2: Download Attachment
                  </span>
                )}
                {step.action === 'find_customer' && (
                  <span className="text-2xs font-mono text-slate-400 bg-surface px-2 py-0.5 rounded">
                    Action 3: Find Customer
                  </span>
                )}
                {step.action === 'update_customer' && (
                  <span className="text-2xs font-mono text-slate-400 bg-surface px-2 py-0.5 rounded">
                    Action 4: Update CRM
                  </span>
                )}
                {step.action === 'send_message' && (
                  <span className="text-2xs font-mono text-slate-400 bg-surface px-2 py-0.5 rounded">
                    Action 5: Slack Notification
                  </span>
                )}
              </div>

              {/* Step Status Badge */}
              <div className="flex items-center gap-2">
                <ExecutionStatusBadge status={step.status} size="sm" />
              </div>
            </div>

            {/* Simulation / Result Summary */}
            <div className="mt-2.5 space-y-1.5 text-xs">
              {step.result_summary && (
                <div className="flex items-start gap-2 text-cyan-300/90 font-mono text-2xs bg-cyan-950/30 p-2.5 rounded-xl border border-cyan-800/40">
                  <ShieldCheck className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
                  <span className="leading-relaxed">
                    {step.result_summary}
                  </span>
                </div>
              )}

              {step.error_summary && (
                <div className="flex items-start gap-2 text-rose-300 font-mono text-2xs bg-rose-950/40 p-2.5 rounded-xl border border-rose-800/50">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <span className="leading-relaxed">
                    {step.error_summary}
                  </span>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
