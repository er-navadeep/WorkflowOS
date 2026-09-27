import React from 'react';
import { 
  X, 
  Sparkles, 
  Clock, 
  Layers, 
  Percent, 
  Activity, 
  Info,
  Calendar,
  Timer,
  CheckCircle2
} from 'lucide-react';
import { WorkflowStatusBadge, IntegrationBadge } from '../workflows/WorkflowComponents';

export function CandidateDetailModal({ candidate, onClose }) {
  if (!candidate) return null;

  const steps = candidate.sequence || candidate.sequence_steps || [];
  const evidence = candidate.evidence || {};
  const applications = candidate.applications || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/75 backdrop-blur-md animate-fadeIn">
      {/* Modal Dialog */}
      <div className="glass-panel w-full max-w-3xl rounded-3xl max-h-[90vh] flex flex-col border border-surface-border shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-6 border-b border-surface-border/80 flex items-start justify-between gap-4 bg-surface/80">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-2xs font-mono uppercase tracking-widest text-cyan-400 font-semibold flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                Discovered Pattern Inspection
              </span>
              <WorkflowStatusBadge status={candidate.status || 'discovered'} />
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">{candidate.name}</h2>
            <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{candidate.description}</p>
          </div>

          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-surface-elevated transition-colors shrink-0"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* ARCHITECTURAL DISTINCTION BANNER */}
          <div className="p-4 rounded-2xl bg-cyan-950/30 border border-cyan-800/50 flex items-start gap-3">
            <Info className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
            <div className="text-xs leading-relaxed">
              <span className="font-semibold text-cyan-300 uppercase tracking-wider block font-mono text-2xs">
                Observed Activity (Not Generated Workflow)
              </span>
              <p className="text-slate-300 mt-1">
                This record represents an empirical pattern clustered directly from user session telemetry. 
                It has not yet undergone AI schema generation (Phase 6) and has no executable automation code.
              </p>
            </div>
          </div>

          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Discovery Score</span>
              <span className="text-lg font-bold text-cyan-400 font-mono mt-0.5 block">
                {typeof candidate.score === 'number' ? candidate.score.toFixed(3) : '—'}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">Composite rating</span>
            </div>

            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Occurrences</span>
              <span className="text-lg font-bold text-white font-mono mt-0.5 block">
                {candidate.occurrence_count || candidate.session_ids?.length || 0}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">Recorded sessions</span>
            </div>

            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Similarity</span>
              <span className="text-lg font-bold text-emerald-400 font-mono mt-0.5 block">
                {typeof candidate.similarity === 'number' ? `${(candidate.similarity * 100).toFixed(0)}%` : '—'}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">Pairwise consistency</span>
            </div>

            <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Sequence Steps</span>
              <span className="text-lg font-bold text-slate-200 font-mono mt-0.5 block">
                {steps.length}
              </span>
              <span className="text-2xs text-slate-500 mt-0.5 block">Action chain length</span>
            </div>
          </div>

          {/* Applications Involved */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono text-2xs">
              Applications Involved
            </h4>
            <div className="flex flex-wrap gap-2">
              {applications.map((app, idx) => (
                <IntegrationBadge key={idx} application={app} />
              ))}
            </div>
          </div>

          {/* Scoring Evidence Breakdown */}
          {evidence && Object.keys(evidence).length > 0 && (
            <div className="p-4 rounded-2xl bg-surface-elevated/40 border border-surface-border space-y-3">
              <h4 className="text-xs font-semibold text-slate-200 flex items-center justify-between">
                <span>Scoring Evidence Breakdown</span>
                <span className="text-2xs font-mono text-slate-500">Normalised Weights</span>
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
                <div className="p-2.5 rounded-lg bg-surface/50 border border-surface-border/50">
                  <span className="text-2xs text-slate-500 block">Occurrence Weight</span>
                  <span className="text-sm font-semibold text-slate-200 mt-0.5 block">
                    {typeof evidence.occurrence_factor === 'number' ? evidence.occurrence_factor.toFixed(2) : '—'}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-surface/50 border border-surface-border/50">
                  <span className="text-2xs text-slate-500 block">Coverage Weight</span>
                  <span className="text-sm font-semibold text-slate-200 mt-0.5 block">
                    {typeof evidence.coverage_factor === 'number' ? evidence.coverage_factor.toFixed(2) : '—'}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-surface/50 border border-surface-border/50">
                  <span className="text-2xs text-slate-500 block">Length Weight</span>
                  <span className="text-sm font-semibold text-slate-200 mt-0.5 block">
                    {typeof evidence.length_factor === 'number' ? evidence.length_factor.toFixed(2) : '—'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Timing Telemetry */}
          <div className="p-4 rounded-2xl bg-surface-elevated/20 border border-surface-border/60 flex flex-wrap items-center justify-between gap-4 text-xs font-mono text-slate-400">
            {candidate.first_seen && (
              <div>
                <span className="text-2xs text-slate-500 block">First Detected</span>
                <span className="text-slate-300">{new Date(candidate.first_seen).toLocaleString()}</span>
              </div>
            )}
            {candidate.last_seen && (
              <div>
                <span className="text-2xs text-slate-500 block">Latest Occurrence</span>
                <span className="text-slate-300">{new Date(candidate.last_seen).toLocaleString()}</span>
              </div>
            )}
            {candidate.average_duration_seconds !== undefined && (
              <div>
                <span className="text-2xs text-slate-500 block">Avg Duration</span>
                <span className="text-slate-300">{candidate.average_duration_seconds.toFixed(2)}s</span>
              </div>
            )}
          </div>

          {/* Observed Sequence Actions */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-slate-200 flex items-center justify-between">
              <span>Sequence of Observed Actions</span>
              <span className="text-2xs font-mono text-slate-500">{steps.length} sequential actions</span>
            </h4>

            <div className="space-y-2">
              {steps.map((st, i) => (
                <div
                  key={st.order || i}
                  className="flex items-center justify-between p-3 rounded-xl bg-surface/60 border border-surface-border hover:border-slate-600 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-lg bg-surface-elevated border border-surface-border flex items-center justify-center text-2xs font-mono font-medium text-slate-400">
                      {st.order || i + 1}
                    </span>
                    <IntegrationBadge application={st.application} />
                    <span className="text-xs font-medium text-slate-200">{st.action}</span>
                  </div>

                  {st.event_type && (
                    <span className="text-2xs font-mono text-slate-500 bg-surface px-2 py-0.5 rounded border border-surface-border/60">
                      {st.event_type}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-surface-border bg-surface/80 flex items-center justify-between">
          <span className="text-2xs font-mono text-slate-500">
            Fingerprint: {candidate.sequence_fingerprint?.slice(0, 16)}...
          </span>

          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold rounded-xl bg-surface-elevated hover:bg-slate-700 text-slate-200 transition-colors"
          >
            Close Details
          </button>
        </div>
      </div>
    </div>
  );
}
