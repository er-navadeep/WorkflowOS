import React, { useState } from 'react';
import { 
  Zap, 
  X, 
  ShieldCheck, 
  Layers, 
  AlertCircle, 
  Loader2,
  MessageSquare,
  CheckCircle2
} from 'lucide-react';
import { WorkflowStatusBadge } from '../workflows/WorkflowComponents';

export function LiveExecutionConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  workflow,
  isExecuting = false,
  error = null,
}) {
  const [notificationText, setNotificationText] = useState('');

  if (!isOpen || !workflow) return null;

  function handleSubmit() {
    const variables = {};
    if (notificationText.trim()) {
      variables.requestNotificationText = notificationText.trim();
      variables.message = notificationText.trim();
    }
    onConfirm(variables);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="w-full max-w-lg rounded-3xl glass-panel border border-emerald-800/60 p-6 sm:p-8 space-y-6 shadow-2xl relative overflow-hidden"
        role="dialog"
        aria-modal="true"
      >
        {/* Glowing backdrop accent */}
        <div className="absolute -top-24 -right-24 w-48 h-48 rounded-full bg-emerald-500/10 blur-3xl pointer-events-none" />

        {/* Modal Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <span className="text-2xs font-mono uppercase tracking-widest text-emerald-400 font-semibold flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5" />
              Live Integration Execution (Phase 8.3)
            </span>
            <h2 className="text-xl sm:text-2xl font-extrabold text-white tracking-tight">
              Execute live workflow?
            </h2>
          </div>

          <button
            onClick={onClose}
            disabled={isExecuting}
            className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors disabled:opacity-50 cursor-pointer"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Live Execution Callout */}
        <div className="p-4 rounded-2xl bg-emerald-950/40 border border-emerald-700/50 space-y-2">
          <div className="flex items-center gap-2 text-emerald-300 font-bold font-mono text-xs uppercase tracking-wider">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>REAL EXTERNAL ACTIONS ENABLED</span>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Supported steps (e.g. <strong>Slack send_message</strong>) will dispatch real requests through the configured integration webhook.
          </p>
        </div>

        {/* Workflow Summary Details */}
        <div className="p-4 rounded-2xl bg-surface/60 border border-surface-border space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 font-medium">Workflow</span>
            <span className="font-semibold text-white truncate max-w-[240px]">
              {workflow.name}
            </span>
          </div>

          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 font-medium">Steps to Execute</span>
            <span className="font-mono font-bold text-emerald-400 flex items-center gap-1">
              <Layers className="w-3.5 h-3.5" />
              {workflow.steps?.length || 0} steps
            </span>
          </div>

          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 font-medium">Workflow Status</span>
            <WorkflowStatusBadge status={workflow.status} />
          </div>
        </div>

        {/* Optional Custom Message Input */}
        <div className="space-y-1.5">
          <label className="text-2xs font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1">
            <MessageSquare className="w-3 h-3 text-emerald-400" />
            Custom Notification Message (Optional)
          </label>
          <input
            type="text"
            value={notificationText}
            onChange={(e) => setNotificationText(e.target.value)}
            placeholder="e.g. Customer support inquiry processed successfully."
            className="w-full px-3.5 py-2.5 rounded-xl bg-surface/80 border border-surface-border text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
          />
        </div>

        {/* Error Callout if execution failed */}
        {error && (
          <div className="p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/60 flex items-start gap-2.5 text-xs text-rose-300">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-semibold block">Execution request failed</span>
              <p className="opacity-90">{error.message || String(error)}</p>
            </div>
          </div>
        )}

        {/* Modal Actions */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isExecuting}
            className="px-4 py-2.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors disabled:opacity-50 cursor-pointer"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={isExecuting}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-600/30 transition-all disabled:opacity-50 cursor-pointer"
          >
            {isExecuting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Executing live workflow...</span>
              </>
            ) : (
              <>
                <Zap className="w-4 h-4 fill-current" />
                <span>Execute Live</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
