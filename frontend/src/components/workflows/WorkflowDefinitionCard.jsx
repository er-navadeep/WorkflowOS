import React from 'react';
import { ArrowRight, Layers, Cpu, Zap, Calendar, CheckCircle2, Clock, XCircle } from 'lucide-react';
import { WorkflowStatusBadge, IntegrationBadge } from './WorkflowComponents';

export function WorkflowDefinitionCard({ workflow, onSelect }) {
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

  // Status helper text per Requirement 7 (Approval Separation)
  const statusHelpers = {
    generated: {
      text: 'Waiting for human approval',
      color: 'text-amber-400 bg-amber-950/40 border-amber-800/40',
      icon: Clock,
    },
    approved: {
      text: 'Approved — ready for future automation',
      color: 'text-emerald-400 bg-emerald-950/40 border-emerald-800/40',
      icon: CheckCircle2,
    },
    rejected: {
      text: 'Rejected',
      color: 'text-rose-400 bg-rose-950/40 border-rose-800/40',
      icon: XCircle,
    },
  };

  const statusHelper = statusHelpers[workflow.status] || {
    text: workflow.status,
    color: 'text-slate-400 bg-surface-elevated/40 border-surface-border',
    icon: Clock,
  };
  const HelperIcon = statusHelper.icon;

  return (
    <div className="glass-card rounded-2xl p-6 flex flex-col justify-between hover:border-slate-600 transition-all group">
      <div>
        {/* Top Header: Name & Status Badge */}
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex-1 min-w-0">
            <span className="text-2xs font-mono uppercase tracking-widest text-primary-400 font-semibold block">
              AI Workflow Definition
            </span>
            <h3 className="text-base font-semibold text-white group-hover:text-primary-300 transition-colors mt-0.5 truncate">
              {workflow.name}
            </h3>
          </div>
          <WorkflowStatusBadge status={workflow.status} />
        </div>

        {/* Workflow Description */}
        <p className="text-xs text-slate-400 line-clamp-2 mb-4 leading-relaxed">
          {workflow.description}
        </p>

        {/* Informational Status Callout (Requirement 7) */}
        <div className={`p-2.5 rounded-xl border text-xs flex items-center gap-2 mb-4 ${statusHelper.color}`}>
          <HelperIcon className="w-3.5 h-3.5 shrink-0" />
          <span className="font-medium truncate">{statusHelper.text}</span>
        </div>

        {/* 4-Stat Metric Box: Confidence, Steps, Integrations, Created */}
        <div className="grid grid-cols-4 gap-2 p-3 rounded-xl bg-surface/70 border border-surface-border mb-4 font-mono text-center">
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
          <div className="p-3 rounded-xl bg-surface-elevated/30 border border-surface-border mb-4">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider">Trigger</span>
              <IntegrationBadge application={workflow.trigger.application} />
            </div>
            <p className="text-xs font-medium text-slate-200 truncate">
              {workflow.trigger.event}
            </p>
          </div>
        )}
      </div>

      {/* Card Footer: Metadata & Action */}
      <div className="pt-4 mt-2 border-t border-surface-border/60 flex items-center justify-between">
        <span className="text-2xs text-slate-500 font-mono">
          ID: {workflow.workflow_id?.slice(0, 8)}...
        </span>

        <button
          onClick={() => onSelect?.(workflow)}
          className="text-xs font-semibold text-primary-400 hover:text-primary-300 flex items-center gap-1.5 group-hover:translate-x-1 transition-transform"
        >
          <span>View workflow</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
