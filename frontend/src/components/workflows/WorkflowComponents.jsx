import React from 'react';
import { 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Sparkles, 
  ArrowRight, 
  Layers, 
  Mail, 
  MessageSquare, 
  Database, 
  Globe, 
  Terminal,
  Zap,
  HelpCircle,
  ShieldCheck
} from 'lucide-react';

export function WorkflowStatusBadge({ status }) {
  const configs = {
    generated: {
      label: 'Generated (Pending Review)',
      classes: 'bg-amber-950/40 text-amber-300 border-amber-800/50 shadow-amber-900/10',
      icon: Clock,
    },
    approved: {
      label: 'Approved',
      classes: 'bg-emerald-950/40 text-emerald-300 border-emerald-800/50 shadow-emerald-900/10',
      icon: CheckCircle2,
    },
    rejected: {
      label: 'Rejected',
      classes: 'bg-rose-950/40 text-rose-300 border-rose-800/50 shadow-rose-900/10',
      icon: XCircle,
    },
    discovered: {
      label: 'Discovered Pattern',
      classes: 'bg-cyan-950/40 text-cyan-300 border-cyan-800/50 shadow-cyan-900/10',
      icon: Sparkles,
    },
  };

  const config = configs[status] || {
    label: status,
    classes: 'bg-slate-800 text-slate-300 border-slate-700',
    icon: HelpCircle,
  };

  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border shadow-sm ${config.classes}`}>
      <Icon className="w-3.5 h-3.5" />
      <span>{config.label}</span>
    </span>
  );
}

export function IntegrationBadge({ application }) {
  const appIcons = {
    gmail: { icon: Mail, color: 'text-red-400 bg-red-950/30 border-red-800/40' },
    slack: { icon: MessageSquare, color: 'text-emerald-400 bg-emerald-950/30 border-emerald-800/40' },
    crm: { icon: Database, color: 'text-blue-400 bg-blue-950/30 border-blue-800/40' },
    browser: { icon: Globe, color: 'text-cyan-400 bg-cyan-950/30 border-cyan-800/40' },
  };

  const normalized = (application || '').toLowerCase();
  const matched = appIcons[normalized] || { icon: Terminal, color: 'text-slate-400 bg-slate-900 border-slate-700' };
  const Icon = matched.icon;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-mono border ${matched.color}`}>
      <Icon className="w-3 h-3" />
      <span>{application}</span>
    </span>
  );
}

export function WorkflowTrigger({ trigger }) {
  if (!trigger) return null;

  return (
    <div className="p-3.5 rounded-xl bg-surface-elevated/40 border border-surface-border flex items-start gap-3">
      <div className="w-8 h-8 rounded-lg bg-primary-950/60 border border-primary-800/50 flex items-center justify-center text-primary-400 shrink-0">
        <Zap className="w-4 h-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-primary-400">Trigger</span>
          <IntegrationBadge application={trigger.application} />
        </div>
        <p className="text-sm font-medium text-slate-200 mt-1 truncate">{trigger.event}</p>
        {trigger.description && (
          <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{trigger.description}</p>
        )}
      </div>
    </div>
  );
}

export function WorkflowStep({ step, isLast, showDetails = true }) {
  const inputs = Array.isArray(step.inputs) ? step.inputs : [];
  const outputs = Array.isArray(step.outputs) ? step.outputs : [];

  return (
    <div className="relative flex items-start gap-3 group">
      {/* Step Number Bubble */}
      <div className="w-7 h-7 rounded-full bg-surface-elevated border border-surface-border group-hover:border-primary-500/50 flex items-center justify-center text-xs font-mono font-bold text-slate-300 shrink-0 transition-colors z-10">
        {step.order}
      </div>

      {/* Step Connector Line */}
      {!isLast && (
        <div className="absolute left-3.5 top-7 bottom-0 w-px bg-surface-border" />
      )}

      {/* Step Card */}
      <div className="flex-1 pb-4">
        <div className="p-3.5 rounded-xl bg-surface/60 border border-surface-border group-hover:border-slate-700 transition-colors space-y-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-white font-mono">{step.action || step.name}</span>
              <IntegrationBadge application={step.application} />
            </div>

            {step.on_failure && (
              <span className={`text-2xs font-mono px-2 py-0.5 rounded border ${
                step.on_failure === 'continue'
                  ? 'text-amber-400 bg-amber-950/30 border-amber-800/40'
                  : step.on_failure === 'human_intervention'
                  ? 'text-cyan-400 bg-cyan-950/30 border-cyan-800/40'
                  : 'text-rose-400 bg-rose-950/30 border-rose-800/40'
              }`}>
                on_failure: {step.on_failure}
              </span>
            )}
          </div>

          {step.description && (
            <p className="text-xs text-slate-300 leading-relaxed">{step.description}</p>
          )}

          {/* Detailed Inputs / Outputs */}
          {showDetails && (inputs.length > 0 || outputs.length > 0) && (
            <div className="pt-2 border-t border-surface-border/50 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-2xs font-mono">
              {inputs.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-slate-500 font-semibold">Inputs:</span>
                  {inputs.map((inp, idx) => (
                    <span key={idx} className="bg-surface-elevated/70 text-cyan-300 px-1.5 py-0.5 rounded border border-surface-border">
                      {inp}
                    </span>
                  ))}
                </div>
              )}
              {outputs.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-slate-500 font-semibold">Outputs:</span>
                  {outputs.map((out, idx) => (
                    <span key={idx} className="bg-surface-elevated/70 text-emerald-300 px-1.5 py-0.5 rounded border border-surface-border">
                      {out}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function WorkflowStepList({ steps = [], showDetails = true }) {
  if (!steps.length) {
    return <p className="text-xs text-slate-500 italic">No execution steps defined.</p>;
  }

  return (
    <div className="space-y-1 mt-2">
      {steps.map((step, idx) => (
        <WorkflowStep 
          key={step.step_id || step.order || idx} 
          step={step} 
          isLast={idx === steps.length - 1} 
          showDetails={showDetails}
        />
      ))}
    </div>
  );
}

export function WorkflowCondition({ condition }) {
  if (!condition) return null;

  return (
    <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-900/30 text-xs space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-amber-400 font-semibold uppercase tracking-wider text-2xs font-mono">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Condition Guard</span>
        </div>
        <span className="text-2xs font-mono text-slate-500">
          ID: {condition.condition_id?.slice(0, 8)}...
        </span>
      </div>

      {condition.description && (
        <p className="text-xs font-medium text-slate-200">{condition.description}</p>
      )}

      {condition.expression && (
        <div className="p-2 rounded bg-surface/60 border border-surface-border font-mono text-xs text-amber-300">
          <span className="text-slate-500 mr-2">EXPR:</span>
          {condition.expression}
        </div>
      )}

      {(condition.on_true || condition.on_false) && (
        <div className="flex items-center gap-3 pt-1 text-2xs font-mono">
          {condition.on_true && (
            <span className="text-slate-300">
              <span className="text-emerald-400 font-bold">ON TRUE:</span> {condition.on_true}
            </span>
          )}
          {condition.on_false && (
            <span className="text-slate-300">
              <span className="text-rose-400 font-bold">ON FALSE:</span> {condition.on_false}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export function WorkflowVariablesList({ variables = [] }) {
  if (!variables.length) {
    return <p className="text-xs text-slate-500 italic">No variables declared in this workflow definition.</p>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {variables.map((v, idx) => (
        <div key={idx} className="p-3 rounded-xl bg-surface/60 border border-surface-border space-y-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-mono font-bold text-cyan-300">{v.name}</span>
            {v.source_step_order && (
              <span className="text-2xs font-mono text-slate-500">Step {v.source_step_order}</span>
            )}
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">{v.description}</p>
        </div>
      ))}
    </div>
  );
}

export function WorkflowIntegrationsList({ integrations = [] }) {
  if (!integrations.length) {
    return <p className="text-xs text-slate-500 italic">No integration dependencies specified.</p>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {integrations.map((item, idx) => (
        <div key={idx} className="p-3.5 rounded-xl bg-surface/60 border border-surface-border space-y-2">
          <div className="flex items-center justify-between">
            <IntegrationBadge application={item.application} />
          </div>
          <p className="text-xs text-slate-300">{item.purpose}</p>
          {Array.isArray(item.required_capabilities) && item.required_capabilities.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-1">
              {item.required_capabilities.map((cap, cIdx) => (
                <span key={cIdx} className="text-2xs font-mono bg-surface-elevated/80 text-slate-400 px-1.5 py-0.5 rounded border border-surface-border">
                  {cap}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function WorkflowErrorHandlingSection({ errorHandling }) {
  if (!errorHandling) return null;

  return (
    <div className="p-4 rounded-xl bg-surface-elevated/30 border border-surface-border space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
        <div className="p-2.5 rounded-lg bg-surface/60 border border-surface-border">
          <span className="text-2xs text-slate-500 uppercase tracking-wider block">On Step Failure</span>
          <span className="text-xs font-semibold text-rose-300 mt-0.5 block">{errorHandling.on_step_failure || 'stop_and_report'}</span>
        </div>
        <div className="p-2.5 rounded-lg bg-surface/60 border border-surface-border">
          <span className="text-2xs text-slate-500 uppercase tracking-wider block">On Missing Input</span>
          <span className="text-xs font-semibold text-amber-300 mt-0.5 block">{errorHandling.on_missing_input || 'stop'}</span>
        </div>
        <div className="p-2.5 rounded-lg bg-surface/60 border border-surface-border">
          <span className="text-2xs text-slate-500 uppercase tracking-wider block">On Timeout</span>
          <span className="text-xs font-semibold text-cyan-300 mt-0.5 block">{errorHandling.on_timeout || 'stop_and_report'}</span>
        </div>
      </div>
      {errorHandling.notes && (
        <p className="text-xs text-slate-400 font-mono leading-relaxed pt-1">
          <span className="text-slate-500 font-semibold mr-1">Policy Note:</span>
          {errorHandling.notes}
        </p>
      )}
    </div>
  );
}

export function WorkflowCard({ workflow, onSelect, compact = false }) {
  return (
    <div 
      onClick={onSelect}
      className={`glass-card rounded-xl p-5 ${onSelect ? 'cursor-pointer' : ''} flex flex-col justify-between`}
    >
      <div>
        <div className="flex items-start justify-between gap-3 mb-2">
          <h3 className="text-base font-semibold text-slate-100 truncate flex-1">
            {workflow.name}
          </h3>
          <WorkflowStatusBadge status={workflow.status} />
        </div>

        <p className="text-xs text-slate-400 line-clamp-2 mb-4 leading-relaxed">
          {workflow.description}
        </p>

        {!compact && workflow.trigger && (
          <div className="mb-4">
            <WorkflowTrigger trigger={workflow.trigger} />
          </div>
        )}
      </div>

      <div className="pt-3 border-t border-surface-border/60 flex items-center justify-between text-xs text-slate-400">
        <div className="flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-slate-500" />
          <span>{workflow.steps?.length || 0} steps</span>
          {workflow.generation_confidence ? (
            <span className="ml-2 font-mono text-cyan-400">
              {(workflow.generation_confidence * 100).toFixed(0)}% conf
            </span>
          ) : null}
        </div>

        {workflow.created_at && (
          <span className="text-slate-500">
            {new Date(workflow.created_at).toLocaleDateString()}
          </span>
        )}
      </div>
    </div>
  );
}
