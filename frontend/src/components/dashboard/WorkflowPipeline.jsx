import React from 'react';
import { 
  Eye, 
  BrainCircuit, 
  Sparkles, 
  Workflow, 
  ShieldCheck, 
  PlayCircle,
  CheckCircle2,
  Clock
} from 'lucide-react';

const PIPELINE_STAGES = [
  {
    key: 'observe',
    label: 'Observe',
    desc: 'Activity events',
    phase: 'Phase 2–3',
    icon: Eye,
    status: 'active',
  },
  {
    key: 'understand',
    label: 'Understand',
    desc: 'AI intent analysis',
    phase: 'Phase 5',
    icon: BrainCircuit,
    status: 'active',
  },
  {
    key: 'discover',
    label: 'Discover',
    desc: 'Pattern clustering',
    phase: 'Phase 4',
    icon: Sparkles,
    status: 'active',
  },
  {
    key: 'generate',
    label: 'Generate',
    desc: 'Workflow schemas',
    phase: 'Phase 6',
    icon: Workflow,
    status: 'active',
  },
  {
    key: 'approve',
    label: 'Approve',
    desc: 'Human governance',
    phase: 'Phase 7',
    icon: ShieldCheck,
    status: 'active',
  },
  {
    key: 'automate',
    label: 'Automate',
    desc: 'Execution engine',
    phase: 'Phase 8',
    icon: PlayCircle,
    status: 'coming_next',
  },
];

export function WorkflowPipeline() {
  return (
    <div className="glass-panel rounded-2xl p-6 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-surface-border/60 pb-3">
        <div>
          <h3 className="text-sm font-semibold text-white tracking-tight flex items-center gap-2">
            <span>Autonomous Workflow Lifecycle</span>
            <span className="px-2 py-0.5 rounded-full text-2xs font-mono font-medium bg-emerald-950/50 text-emerald-400 border border-emerald-800/40">
              Phases 2–7 Verified
            </span>
          </h3>
          <p className="text-2xs text-slate-400 mt-0.5">
            WorkFlowOS observes raw digital activities, clusters repetitive routines, generates formal automation definitions, and enforces human sign-off before automation.
          </p>
        </div>
      </div>

      {/* Horizontal Pipeline Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 pt-1">
        {PIPELINE_STAGES.map((stage, index) => {
          const Icon = stage.icon;
          const isImplemented = stage.status === 'active';

          return (
            <div
              key={stage.key}
              className={`relative rounded-xl p-3.5 border transition-all flex flex-col justify-between ${
                isImplemented
                  ? 'bg-surface-elevated/40 border-surface-border hover:border-slate-600'
                  : 'bg-surface/30 border-dashed border-surface-border/60 opacity-80'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-2.5">
                  <div
                    className={`w-7 h-7 rounded-lg flex items-center justify-center ${
                      isImplemented
                        ? 'bg-primary-950/60 border border-primary-800/50 text-primary-400'
                        : 'bg-slate-900 border border-slate-800 text-slate-500'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                  </div>

                  {isImplemented ? (
                    <span className="flex items-center gap-1 text-emerald-400 text-2xs font-medium">
                      <CheckCircle2 className="w-3 h-3" />
                      <span className="hidden sm:inline">Ready</span>
                    </span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded text-2xs font-mono font-semibold bg-indigo-950/60 text-indigo-300 border border-indigo-800/50">
                      Coming next
                    </span>
                  )}
                </div>

                <h4 className="text-xs font-semibold text-slate-200">{stage.label}</h4>
                <p className="text-2xs text-slate-400 mt-0.5 line-clamp-1">{stage.desc}</p>
              </div>

              <div className="mt-3 pt-2 border-t border-surface-border/40 flex items-center justify-between text-2xs text-slate-500 font-mono">
                <span>0{index + 1}</span>
                <span>{stage.phase}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
