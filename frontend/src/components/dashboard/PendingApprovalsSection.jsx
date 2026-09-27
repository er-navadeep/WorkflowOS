import React from 'react';
import { Link } from 'react-router-dom';
import { 
  CheckSquare, 
  ArrowRight, 
  Clock, 
  Layers, 
  Zap, 
  CheckCircle2, 
  HelpCircle 
} from 'lucide-react';
import { IntegrationBadge } from '../workflows/WorkflowComponents';
import { EmptyState } from '../common/FeedbackStates';

export function PendingApprovalsSection({ workflows = [] }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400">
            <CheckSquare className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-200">Pending Approvals</h3>
            <p className="text-2xs text-slate-400">Generated workflow proposals awaiting human review</p>
          </div>
        </div>

        <Link
          to="/approvals"
          className="text-xs text-primary-400 hover:text-primary-300 font-medium flex items-center gap-1 group"
        >
          <span>Open approvals queue</span>
          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
        </Link>
      </div>

      {workflows.length === 0 ? (
        <EmptyState
          icon={CheckCircle2}
          title="No workflows waiting for approval"
          description="WorkFlowOS will show generated workflows here when they are ready for your review."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {workflows.map((wf) => {
            const triggerApp = wf.trigger?.application;
            const stepsCount = wf.steps?.length || 0;
            const integrations = wf.integrations || [];
            const confidence = typeof wf.generation_confidence === 'number'
              ? `${(wf.generation_confidence * 100).toFixed(0)}%`
              : null;

            return (
              <div
                key={wf.workflow_id}
                className="glass-card rounded-2xl p-5 flex flex-col justify-between hover:border-slate-600 transition-all group"
              >
                <div>
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <h4 className="text-sm font-semibold text-white group-hover:text-primary-300 transition-colors line-clamp-1">
                      {wf.name}
                    </h4>
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-2xs font-semibold bg-amber-950/60 text-amber-300 border border-amber-800/50 shrink-0">
                      <Clock className="w-3 h-3" />
                      <span>Needs review</span>
                    </span>
                  </div>

                  <p className="text-xs text-slate-400 line-clamp-2 mb-4 leading-relaxed">
                    {wf.description}
                  </p>

                  {/* Trigger application pill */}
                  {wf.trigger && (
                    <div className="flex items-center gap-2 p-2.5 rounded-xl bg-surface/70 border border-surface-border text-xs mb-3">
                      <Zap className="w-3.5 h-3.5 text-primary-400 shrink-0" />
                      <span className="text-2xs text-slate-400">Trigger:</span>
                      <IntegrationBadge application={triggerApp} />
                      <span className="text-2xs text-slate-300 truncate font-mono">
                        {wf.trigger.event}
                      </span>
                    </div>
                  )}

                  {/* Integrations */}
                  {integrations.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap mb-3">
                      <span className="text-2xs text-slate-500 font-mono">Apps:</span>
                      {integrations.map((item, idx) => (
                        <IntegrationBadge 
                          key={idx} 
                          application={item.application || item.name} 
                        />
                      ))}
                    </div>
                  )}
                </div>

                <div className="pt-3 border-t border-surface-border/60 flex items-center justify-between text-2xs">
                  <div className="flex items-center gap-3 text-slate-400">
                    <span className="flex items-center gap-1">
                      <Layers className="w-3 h-3 text-slate-500" />
                      <span>{stepsCount} steps</span>
                    </span>
                    {confidence && (
                      <span className="text-cyan-400 font-mono">
                        {confidence} confidence
                      </span>
                    )}
                  </div>

                  <Link
                    to="/approvals"
                    className="font-medium text-primary-400 hover:text-primary-300 flex items-center gap-1"
                  >
                    <span>Review workflow</span>
                    <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
