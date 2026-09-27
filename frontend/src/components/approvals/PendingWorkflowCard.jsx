import React from 'react';
import { 
  CheckCircle2, 
  XCircle, 
  Eye, 
  Cpu, 
  Clock, 
  Layers, 
  Zap, 
  ArrowRight,
  Database
} from 'lucide-react';
import { WorkflowStatusBadge, IntegrationBadge } from '../workflows/WorkflowComponents';

export function PendingWorkflowCard({ workflow, onView, onApprove, onReject }) {
  if (!workflow) return null;

  const stepsCount = workflow.steps?.length || 0;
  const integrationsCount = workflow.integrations?.length || 0;
  const confidence = typeof workflow.generation_confidence === 'number'
    ? `${(workflow.generation_confidence * 100).toFixed(0)}%`
    : '—';

  const createdDate = workflow.created_at
    ? new Date(workflow.created_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : '—';

  return (
    <div className="glass-card rounded-2xl p-6 flex flex-col justify-between hover:border-slate-600 transition-all border border-surface-border">
      <div className="space-y-4">
        {/* Card Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <span className="text-2xs font-mono uppercase tracking-widest text-amber-400 font-semibold flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              Awaiting Human Approval
            </span>
            <h3 className="text-base font-bold text-white mt-1 truncate">
              {workflow.name}
            </h3>
          </div>
          <WorkflowStatusBadge status={workflow.status || 'generated'} />
        </div>

        {/* Description */}
        <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
          {workflow.description}
        </p>

        {/* 4-Stat Metric Box */}
        <div className="grid grid-cols-4 gap-2 p-3 rounded-xl bg-surface/70 border border-surface-border font-mono text-center">
          <div className="border-r border-surface-border/60 pr-1">
            <span className="text-2xs text-slate-500 uppercase tracking-wider block">Confidence</span>
            <span className="text-sm font-bold text-cyan-400 mt-0.5 block">{confidence}</span>
          </div>
          <div className="border-r border-surface-border/60 px-1">
            <span className="text-2xs text-slate-500 uppercase tracking-wider block">Actions</span>
            <span className="text-sm font-bold text-white mt-0.5 block">{stepsCount === 6 ? '5 (6 tech)' : stepsCount}</span>
          </div>
          <div className="border-r border-surface-border/60 px-1">
            <span className="text-2xs text-slate-500 uppercase tracking-wider block">Integrations</span>
            <span className="text-sm font-bold text-indigo-400 mt-0.5 block">{integrationsCount}</span>
          </div>
          <div className="pl-1">
            <span className="text-2xs text-slate-500 uppercase tracking-wider block">Created</span>
            <span className="text-2xs font-bold text-slate-300 mt-1 block truncate">{createdDate}</span>
          </div>
        </div>

        {/* Trigger Summary */}
        {workflow.trigger && (
          <div className="p-3 rounded-xl bg-surface-elevated/30 border border-surface-border">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider flex items-center gap-1">
                <Zap className="w-3 h-3 text-amber-400" />
                Trigger Event
              </span>
              <IntegrationBadge application={workflow.trigger.application} />
            </div>
            <p className="text-xs font-medium text-slate-200 truncate">
              {workflow.trigger.event}
            </p>
          </div>
        )}
      </div>

      {/* Action Footer */}
      <div className="pt-5 mt-5 border-t border-surface-border/80 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        {/* View Workflow Action */}
        <button
          onClick={() => onView(workflow)}
          className="px-3.5 py-2 text-xs font-semibold rounded-xl bg-surface-elevated hover:bg-slate-700 text-slate-200 border border-surface-border transition-colors flex items-center justify-center gap-1.5"
        >
          <Eye className="w-3.5 h-3.5 text-cyan-400" />
          <span>View Workflow</span>
        </button>

        {/* Decision Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onReject(workflow)}
            className="flex-1 sm:flex-initial px-3.5 py-2 text-xs font-semibold rounded-xl bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 border border-rose-800/50 transition-colors flex items-center justify-center gap-1.5"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Reject</span>
          </button>

          <button
            onClick={() => onApprove(workflow)}
            className="flex-1 sm:flex-initial px-4 py-2 text-xs font-semibold rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/20 transition-all flex items-center justify-center gap-1.5"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Approve</span>
          </button>
        </div>
      </div>
    </div>
  );
}
