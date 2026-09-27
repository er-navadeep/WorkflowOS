import React from 'react';
import { 
  X, 
  Cpu, 
  Clock, 
  Zap, 
  Layers, 
  ShieldCheck, 
  Variable, 
  Database, 
  AlertTriangle,
  CheckCircle2, 
  XCircle,
  Calendar
} from 'lucide-react';
import { 
  WorkflowStatusBadge, 
  WorkflowTrigger, 
  WorkflowStepList, 
  WorkflowCondition,
  WorkflowVariablesList,
  WorkflowIntegrationsList,
  WorkflowErrorHandlingSection 
} from '../workflows/WorkflowComponents';

export function ReviewWorkflowModal({ workflow, onClose, onApprove, onReject }) {
  if (!workflow) return null;

  const confidencePct = typeof workflow.generation_confidence === 'number'
    ? `${(workflow.generation_confidence * 100).toFixed(0)}%`
    : '—';

  const createdDate = workflow.created_at
    ? new Date(workflow.created_at).toLocaleString('en-US', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : '—';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/75 backdrop-blur-md animate-fadeIn">
      <div className="glass-panel w-full max-w-4xl rounded-3xl max-h-[90vh] flex flex-col border border-surface-border shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="p-6 border-b border-surface-border/80 flex items-start justify-between gap-4 bg-surface/80">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-2xs font-mono uppercase tracking-widest text-primary-400 font-bold flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5" />
                AI-GENERATED WORKFLOW
              </span>
              <span className="text-slate-600">•</span>
              <span className="text-2xs font-mono uppercase tracking-wider text-amber-400 font-medium">
                Awaiting human approval
              </span>
              <WorkflowStatusBadge status={workflow.status || 'generated'} />
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">{workflow.name}</h2>
            <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{workflow.description}</p>
          </div>

          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-surface-elevated transition-colors shrink-0"
            aria-label="Close review modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Trust & Governance Notice */}
          <div className="p-4 rounded-2xl bg-amber-950/20 border border-amber-800/40 flex items-start gap-3">
            <Clock className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="text-xs leading-relaxed">
              <span className="font-semibold text-amber-300 uppercase tracking-wider block font-mono text-2xs">
                Human Governance Gate
              </span>
              <p className="text-slate-300 mt-1">
                You are inspecting the complete definition generated from observed patterns. 
                Verify the trigger, action steps, variables, and error policies before making your approval decision.
              </p>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Confidence</span>
              <span className="text-lg font-bold text-cyan-400 font-mono mt-0.5 block">{confidencePct}</span>
              <span className="text-2xs text-slate-500 mt-0.5 block">AI match score</span>
            </div>

            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Business Actions</span>
              <span className="text-lg font-bold text-white font-mono mt-0.5 block">
                {workflow.steps?.length === 6 ? '5 Actions' : (workflow.steps?.length || 0)}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">
                {workflow.steps?.length === 6 ? '6 technical steps' : 'Operations'}
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">AI Model</span>
              <span className="text-xs font-bold text-indigo-300 font-mono mt-1.5 block truncate">
                {workflow.model_used || 'Gemini'}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">Synthesis model</span>
            </div>

            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Generated At</span>
              <span className="text-2xs font-bold text-slate-300 font-mono mt-1.5 block truncate">
                {createdDate}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">UTC timestamp</span>
            </div>
          </div>

          {/* Trigger */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono text-2xs flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-primary-400" />
              Trigger Specification
            </h4>
            {workflow.trigger ? (
              <WorkflowTrigger trigger={workflow.trigger} />
            ) : (
              <p className="text-xs text-slate-500 italic">No trigger defined.</p>
            )}
          </div>

          {/* Action Pipeline Steps */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono text-2xs flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-cyan-400" />
                Action Pipeline (5 Business Actions / 6 Technical Steps)
              </span>
            </h4>
            <WorkflowStepList steps={workflow.steps} showDetails={true} />
          </div>

          {/* Conditions */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono text-2xs flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
              Conditions ({workflow.conditions?.length || 0})
            </h4>
            {workflow.conditions && workflow.conditions.length > 0 ? (
              <div className="space-y-2">
                {workflow.conditions.map((cond, i) => (
                  <WorkflowCondition key={cond.condition_id || i} condition={cond} />
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic p-3 rounded-xl bg-surface/50 border border-surface-border">
                No conditional guards defined.
              </p>
            )}
          </div>

          {/* Variables */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono text-2xs flex items-center gap-1.5">
              <Variable className="w-3.5 h-3.5 text-indigo-400" />
              Workflow Variables ({workflow.variables?.length || 0})
            </h4>
            <WorkflowVariablesList variables={workflow.variables} />
          </div>

          {/* Integrations */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono text-2xs flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-emerald-400" />
              Required Integrations ({workflow.integrations?.length || 0})
            </h4>
            <WorkflowIntegrationsList integrations={workflow.integrations} />
          </div>

          {/* Error Handling */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono text-2xs flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
              Error Handling Policy
            </h4>
            <WorkflowErrorHandlingSection errorHandling={workflow.error_handling} />
          </div>
        </div>

        {/* Modal Footer with Direct Decision Triggers */}
        <div className="p-4 border-t border-surface-border bg-surface/80 flex items-center justify-between gap-3">
          <span className="text-2xs font-mono text-slate-500">
            ID: {workflow.workflow_id}
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium rounded-xl text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors"
            >
              Close
            </button>
            <button
              onClick={() => {
                onClose();
                onReject(workflow);
              }}
              className="px-4 py-2 text-xs font-semibold rounded-xl bg-rose-950/50 hover:bg-rose-900/60 text-rose-300 border border-rose-800/60 transition-colors flex items-center gap-1.5"
            >
              <XCircle className="w-3.5 h-3.5" />
              <span>Reject</span>
            </button>
            <button
              onClick={() => {
                onClose();
                onApprove(workflow);
              }}
              className="px-5 py-2 text-xs font-semibold rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/20 transition-all flex items-center gap-1.5"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Approve Workflow</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
