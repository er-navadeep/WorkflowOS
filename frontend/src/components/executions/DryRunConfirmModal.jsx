import React from 'react';
import { 
  Play, 
  X, 
  ShieldCheck, 
  Layers, 
  AlertCircle, 
  Loader2 
} from 'lucide-react';
import { WorkflowStatusBadge } from '../workflows/WorkflowComponents';

export function DryRunConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  workflow,
  isExecuting = false,
  error = null,
}) {
  if (!isOpen || !workflow) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="w-full max-w-lg rounded-3xl glass-panel border border-cyan-800/60 p-6 sm:p-8 space-y-6 shadow-2xl relative overflow-hidden"
        role="dialog"
        aria-modal="true"
      >
        {/* Glowing backdrop accent */}
        <div className="absolute -top-24 -right-24 w-48 h-48 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none" />

        {/* Modal Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <span className="text-2xs font-mono uppercase tracking-widest text-cyan-400 font-semibold flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5" />
              Safe Simulation Mode
            </span>
            <h2 className="text-xl sm:text-2xl font-extrabold text-white tracking-tight">
              Run workflow simulation?
            </h2>
          </div>

          <button
            onClick={onClose}
            disabled={isExecuting}
            className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors disabled:opacity-50"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Simulation Guarantee Banner */}
        <div className="p-4 rounded-2xl bg-cyan-950/40 border border-cyan-700/50 space-y-2">
          <div className="flex items-center gap-2 text-cyan-300 font-bold font-mono text-xs uppercase tracking-wider">
            <ShieldCheck className="w-4 h-4 text-cyan-400 shrink-0" />
            <span>DRY RUN — No external actions will be performed</span>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            This will simulate every workflow step without sending emails, modifying CRM records, posting messages, or performing external actions.
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
            <span className="text-slate-400 font-medium">Steps to Simulate</span>
            <span className="font-mono font-bold text-cyan-400 flex items-center gap-1">
              <Layers className="w-3.5 h-3.5" />
              {workflow.steps?.length || 0} steps
            </span>
          </div>

          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 font-medium">Workflow Status</span>
            <WorkflowStatusBadge status={workflow.status} />
          </div>
        </div>

        {/* Error Callout if execution failed */}
        {error && (
          <div className="p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/60 flex items-start gap-2.5 text-xs text-rose-300">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-semibold block">Simulation request failed</span>
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
            className="px-4 py-2.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors disabled:opacity-50"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={onConfirm}
            disabled={isExecuting}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-cyan-600 hover:bg-cyan-500 shadow-lg shadow-cyan-600/30 transition-all disabled:opacity-50"
          >
            {isExecuting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Running workflow simulation...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>Run Dry Run</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
