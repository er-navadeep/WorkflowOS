import React, { useState } from 'react';
import { 
  X, 
  ShieldCheck, 
  Layers, 
  Clock, 
  Calendar, 
  Copy, 
  Check, 
  AlertTriangle,
  Cpu,
  Zap,
  AlertCircle,
  User,
  Mail
} from 'lucide-react';
import { ExecutionStatusBadge, ExecutionModeBadge } from './ExecutionStatusBadge';
import { ExecutionStepList } from './ExecutionStepList';

export function ExecutionDetailModal({
  isOpen,
  onClose,
  execution,
}) {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !execution) return null;

  function copyExecutionId() {
    if (!execution?.execution_id) return;
    navigator.clipboard?.writeText(execution.execution_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const startedDate = execution.started_at
    ? new Date(execution.started_at).toLocaleString('en-US', {
        dateStyle: 'medium',
        timeStyle: 'medium',
      })
    : '—';

  const completedDate = execution.completed_at
    ? new Date(execution.completed_at).toLocaleString('en-US', {
        dateStyle: 'medium',
        timeStyle: 'medium',
      })
    : '—';

  // Duration calculation
  let durationStr = '—';
  if (execution.started_at && execution.completed_at) {
    const diffMs = Math.max(0, new Date(execution.completed_at) - new Date(execution.started_at));
    durationStr = diffMs < 1000 ? `${diffMs}ms` : `${(diffMs / 1000).toFixed(2)}s`;
  }

  const isCompleted = execution.status === 'completed';
  const isFailed = execution.status === 'failed';
  const isNeedsIntervention = execution.status === 'needs_intervention';
  const isLive = execution.mode === 'live';
  const isAuto = execution.trigger_info?.source === 'automatic_trigger' || execution.idempotency_key?.startsWith('trigger:');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/85 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="w-full max-w-3xl max-h-[90vh] flex flex-col rounded-3xl glass-panel border border-surface-border shadow-2xl overflow-hidden"
        role="dialog"
        aria-modal="true"
      >
        {/* Modal Header */}
        <div className="p-6 border-b border-surface-border/80 flex items-start justify-between gap-4 bg-surface/50 shrink-0">
          <div className="space-y-1.5 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <ExecutionModeBadge mode={execution.mode} />
              {isAuto ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-mono font-semibold rounded-full bg-indigo-950/60 text-indigo-300 border border-indigo-700/60 shadow-sm">
                  <Zap className="w-3.5 h-3.5 text-indigo-400" />
                  <span>AUTOMATIC</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-mono font-medium rounded-full bg-slate-800 text-slate-300 border border-slate-700 shadow-sm">
                  <User className="w-3.5 h-3.5 text-slate-400" />
                  <span>MANUAL</span>
                </span>
              )}
              <ExecutionStatusBadge status={execution.status} />
            </div>
            <h2 className="text-xl sm:text-2xl font-extrabold text-white tracking-tight truncate">
              {execution.workflow_name || 'Workflow Execution'}
            </h2>
            <div className="flex items-center gap-2 text-2xs font-mono text-slate-400">
              <span>Execution ID:</span>
              <span className="text-slate-200 bg-surface px-2 py-0.5 rounded border border-surface-border truncate max-w-[220px]">
                {execution.execution_id}
              </span>
              <button
                onClick={copyExecutionId}
                className="p-1 text-slate-400 hover:text-white transition-colors"
                title="Copy execution ID"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors shrink-0"
            aria-label="Close dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="p-6 space-y-6 overflow-y-auto flex-1">
          {/* Outcome Banner */}
          {isCompleted && (
            <div className="p-4 rounded-2xl bg-emerald-950/30 border border-emerald-800/50 flex items-start gap-3">
              <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
              <div className="text-xs leading-relaxed">
                <span className="font-bold text-emerald-300 uppercase tracking-wider block font-mono text-2xs">
                  {isLive ? 'Live Execution Completed' : 'Dry Run Completed'}
                </span>
                <p className="text-slate-300 mt-0.5">
                  All {execution.completed_steps} of {execution.total_steps} steps {isLive ? 'executed' : 'simulated'} successfully. 
                  {isLive ? (
                    <span className="font-semibold text-emerald-300 ml-1">
                      Real external system updates were applied safely.
                    </span>
                  ) : (
                    <span className="font-semibold text-emerald-300 ml-1">
                      No external actions were performed.
                    </span>
                  )}
                </p>
              </div>
            </div>
          )}

          {isNeedsIntervention && (
            <div className="p-4 rounded-2xl bg-purple-950/40 border border-purple-800/60 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-purple-400 shrink-0 mt-0.5" />
              <div className="text-xs leading-relaxed space-y-1">
                <span className="font-bold text-purple-300 uppercase tracking-wider block font-mono text-2xs">
                  Human Intervention Required
                </span>
                <p className="text-purple-200">
                  {execution.error_information || 'The workflow encountered an ambiguous condition (e.g. customer not found in CRM) and safely paused execution to prevent unsafe automated updates.'}
                </p>
                {execution.failed_step && (
                  <p className="text-2xs font-mono text-purple-300/80">
                    Paused at step order: #{execution.failed_step}
                  </p>
                )}
              </div>
            </div>
          )}

          {isFailed && (
            <div className="p-4 rounded-2xl bg-rose-950/40 border border-rose-800/60 flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div className="text-xs leading-relaxed space-y-1">
                <span className="font-bold text-rose-300 uppercase tracking-wider block font-mono text-2xs">
                  {isLive ? 'Live Execution Failed' : 'Dry Run Failed'}
                </span>
                <p className="text-rose-200">
                  {execution.error_information || 'The execution encountered an error.'}
                </p>
                {execution.failed_step && (
                  <p className="text-2xs font-mono text-rose-300/80">
                    Failed at step order: #{execution.failed_step}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Automatic Trigger Metadata Panel (if auto triggered) */}
          {isAuto && (
            <div className="p-4 rounded-2xl bg-indigo-950/30 border border-indigo-800/50 space-y-2">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-indigo-400" />
                <span className="text-xs font-bold text-indigo-200 uppercase tracking-wider font-mono">
                  Automatic Trigger Source Event
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-2xs font-mono pt-1">
                <div className="text-slate-300">
                  <span className="text-slate-500">Source: </span>
                  <span className="text-indigo-300">{execution.trigger_info?.source_app || 'Gmail'}</span>
                </div>
                {execution.trigger_info?.event_identifier && (
                  <div className="text-slate-300 truncate">
                    <span className="text-slate-500">Event ID: </span>
                    <span className="text-slate-200">{execution.trigger_info.event_identifier}</span>
                  </div>
                )}
                {execution.trigger_info?.email_sender && (
                  <div className="text-slate-300 truncate">
                    <span className="text-slate-500">Sender: </span>
                    <span className="text-slate-200">{execution.trigger_info.email_sender}</span>
                  </div>
                )}
                {execution.trigger_info?.email_subject && (
                  <div className="text-slate-300 truncate">
                    <span className="text-slate-500">Subject: </span>
                    <span className="text-slate-200">"{execution.trigger_info.email_subject}"</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Execution Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Steps Progress</span>
              <span className="text-base font-bold text-cyan-400 font-mono mt-0.5 block">
                {execution.completed_steps || 0} / {execution.total_steps || 0}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">Simulated steps</span>
            </div>

            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Duration</span>
              <span className="text-base font-bold text-indigo-300 font-mono mt-0.5 block">
                {durationStr}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">Total run time</span>
            </div>

            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Started</span>
              <span className="text-2xs font-bold text-slate-300 font-mono mt-1 block truncate">
                {startedDate}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">Launch timestamp</span>
            </div>

            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Completed</span>
              <span className="text-2xs font-bold text-slate-300 font-mono mt-1 block truncate">
                {completedDate}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">Finish timestamp</span>
            </div>
          </div>

          {/* Step-by-Step Execution Records */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                  Step-by-Step Simulation Records
                </h3>
              </div>
              <span className="text-2xs font-mono text-slate-400">
                {execution.step_records?.length || 0} record{execution.step_records?.length === 1 ? '' : 's'}
              </span>
            </div>

            <ExecutionStepList steps={execution.step_records || []} />
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-surface-border/80 flex items-center justify-between bg-surface/40 shrink-0">
          <span className="text-2xs font-mono text-slate-500">
            WorkFlowOS Safe Simulation Engine
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-semibold bg-surface-elevated hover:bg-slate-700 text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
