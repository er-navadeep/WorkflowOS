import React from 'react';
import { ArrowRight, Layers, Repeat, Percent, Sparkles } from 'lucide-react';
import { WorkflowStatusBadge, IntegrationBadge } from '../workflows/WorkflowComponents';

export function CandidateCard({ candidate, onSelect }) {
  const steps = candidate.sequence || candidate.sequence_steps || [];
  const scoreFormatted = typeof candidate.score === 'number' ? candidate.score.toFixed(2) : '—';
  const occurrences = candidate.occurrence_count || candidate.session_ids?.length || 0;
  const similarityPct = typeof candidate.similarity === 'number' ? `${(candidate.similarity * 100).toFixed(0)}%` : '—';
  const applications = candidate.applications || [];

  return (
    <div className="glass-card rounded-2xl p-6 flex flex-col justify-between hover:border-slate-600 transition-all group">
      <div>
        {/* Top Header */}
        <div className="flex items-start justify-between gap-3 mb-2">
          <div>
            <span className="text-2xs font-mono uppercase tracking-widest text-cyan-400 font-medium block">
              Repeated Pattern
            </span>
            <h3 className="text-base font-semibold text-white group-hover:text-cyan-300 transition-colors mt-0.5">
              {candidate.name}
            </h3>
          </div>
          <WorkflowStatusBadge status={candidate.status || 'discovered'} />
        </div>

        {/* Why it was detected */}
        <p className="text-xs text-slate-400 line-clamp-2 mb-5 leading-relaxed">
          {candidate.description || 'Repeated pattern detected through session sequence normalization and Jaccard similarity scoring.'}
        </p>

        {/* 4-Stat Metric Box */}
        <div className="grid grid-cols-4 gap-2 p-3 rounded-xl bg-surface/70 border border-surface-border mb-4 font-mono text-center">
          <div className="border-r border-surface-border/60 pr-1">
            <span className="text-2xs text-slate-500 uppercase tracking-wider block">Score</span>
            <span className="text-sm font-bold text-cyan-400 mt-0.5 block">{scoreFormatted}</span>
          </div>
          <div className="border-r border-surface-border/60 px-1">
            <span className="text-2xs text-slate-500 uppercase tracking-wider block">Occurrences</span>
            <span className="text-sm font-bold text-white mt-0.5 block">{occurrences}</span>
          </div>
          <div className="border-r border-surface-border/60 px-1">
            <span className="text-2xs text-slate-500 uppercase tracking-wider block">Similarity</span>
            <span className="text-sm font-bold text-emerald-400 mt-0.5 block">{similarityPct}</span>
          </div>
          <div className="pl-1">
            <span className="text-2xs text-slate-500 uppercase tracking-wider block">Steps</span>
            <span className="text-sm font-bold text-slate-300 mt-0.5 block">{steps.length}</span>
          </div>
        </div>

        {/* Applications Involved */}
        <div className="space-y-1.5 mb-4">
          <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">
            Applications Involved
          </span>
          <div className="flex flex-wrap gap-1.5">
            {applications.map((app, idx) => (
              <IntegrationBadge key={idx} application={app} />
            ))}
          </div>
        </div>

        {/* Sequence Flow Preview */}
        {applications.length > 0 && (
          <div className="p-2.5 rounded-xl bg-surface-elevated/30 border border-surface-border text-2xs font-mono text-slate-400 flex items-center gap-2 overflow-x-auto">
            <span className="text-slate-500 shrink-0">Flow:</span>
            {applications.map((app, idx) => (
              <React.Fragment key={idx}>
                <span className="text-slate-300 font-medium shrink-0">{app}</span>
                {idx < applications.length - 1 && (
                  <span className="text-slate-600 shrink-0">→</span>
                )}
              </React.Fragment>
            ))}
          </div>
        )}
      </div>

      {/* Card Footer with Details Action */}
      <div className="pt-4 mt-4 border-t border-surface-border/60 flex items-center justify-between">
        <span className="text-2xs text-slate-500 font-mono">
          ID: {candidate.candidate_id?.slice(0, 8)}...
        </span>

        <button
          onClick={() => onSelect(candidate)}
          className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 flex items-center gap-1.5 group-hover:translate-x-0.5 transition-transform"
        >
          <span>View details</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
