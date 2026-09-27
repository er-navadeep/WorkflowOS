import React, { useEffect, useState } from 'react';
import { 
  Sparkles, 
  Repeat, 
  Layers, 
  RefreshCw, 
  Info,
  CheckCircle2,
  Grid,
  Filter
} from 'lucide-react';
import { api } from '../../services/api/client';
import { CandidateCard } from '../../components/discovery/CandidateCard';
import { CandidateDetailModal } from '../../components/discovery/CandidateDetailModal';
import { IntegrationBadge } from '../../components/workflows/WorkflowComponents';
import { ErrorState, EmptyState } from '../../components/common/FeedbackStates';

export function DiscoveryPage() {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);

  useEffect(() => {
    loadCandidates();
  }, []);

  async function loadCandidates() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getCandidates();
      setCandidates(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load discovery candidates:', err);
      setError(new Error("Unable to load discovered workflows."));
    } finally {
      setLoading(false);
    }
  }

  async function handleRunDiscovery() {
    setRunning(true);
    try {
      await api.runDiscovery();
      await loadCandidates();
    } catch (err) {
      alert(`Discovery engine error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  }

  // Calculate summary metrics strictly from backend candidate data
  const totalPatterns = candidates.length;
  const repeatedWorkflows = candidates.filter(
    (c) => (c.occurrence_count || c.session_ids?.length || 0) >= 2
  ).length;

  // Extract unique applications involved
  const uniqueApps = Array.from(
    new Set(candidates.flatMap((c) => c.applications || []))
  );

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* 1. Page Header & Explanatory Section */}
      <section className="space-y-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Workflow Discovery
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            WorkFlowOS found these repetitive patterns in your activity.
          </p>
        </div>

        {/* Explanatory Banner */}
        <div className="p-4 rounded-2xl glass-panel border border-surface-border flex items-start gap-3">
          <div className="p-2 rounded-xl bg-cyan-950/60 border border-cyan-800/50 text-cyan-400 shrink-0 mt-0.5">
            <Info className="w-4 h-4" />
          </div>
          <div className="text-xs text-slate-300 leading-relaxed flex-1">
            <span className="font-semibold text-white block">Pattern Recognition Engine</span>
            These workflows are automatically identified from repeated activity across your applications. 
            The discovery engine groups sessions by sequential fingerprint and computes pairwise Jaccard similarity.
          </div>
          <button
            onClick={handleRunDiscovery}
            disabled={running}
            className="hidden sm:inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-xl bg-primary-600/80 hover:bg-primary-600 text-white border border-primary-500/40 transition-all shrink-0 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${running ? 'animate-spin' : ''}`} />
            <span>{running ? 'Scanning...' : 'Re-run Discovery'}</span>
          </button>
        </div>
      </section>

      {/* 2. Summary Section */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Discovered Patterns</span>
            <div className="p-2 rounded-xl bg-cyan-950/40 border border-cyan-800/50 text-cyan-400">
              <Sparkles className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-white font-mono">
              {loading ? '—' : totalPatterns}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Total candidate clusters found</p>
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Repeated Workflows</span>
            <div className="p-2 rounded-xl bg-indigo-950/40 border border-indigo-800/50 text-indigo-400">
              <Repeat className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-white font-mono">
              {loading ? '—' : repeatedWorkflows}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Patterns with 2+ occurrences</p>
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Applications Involved</span>
            <div className="p-2 rounded-xl bg-emerald-950/40 border border-emerald-800/50 text-emerald-400">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-white font-mono">
              {loading ? '—' : uniqueApps.length}
            </span>
            <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
              {uniqueApps.length > 0 ? (
                uniqueApps.map((app, i) => (
                  <IntegrationBadge key={i} application={app} />
                ))
              ) : (
                <span className="text-2xs text-slate-400">No applications detected</span>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* 3. Discovered Candidate Cards List */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-200">Discovered Workflow Candidates</h3>
          </div>
          <span className="text-2xs font-mono text-slate-400">
            {candidates.length} candidate{candidates.length === 1 ? '' : 's'} available
          </span>
        </div>

        {/* Loading State with Skeleton Cards */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 animate-pulse">
            {[1, 2].map((i) => (
              <div key={i} className="glass-card rounded-2xl p-6 h-64 flex flex-col justify-between">
                <div className="space-y-3">
                  <div className="h-4 w-32 bg-surface-elevated rounded" />
                  <div className="h-6 w-48 bg-surface-elevated rounded" />
                  <div className="h-3 w-full bg-surface-elevated rounded" />
                </div>
                <div className="h-12 w-full bg-surface-elevated/40 rounded-xl" />
                <div className="h-4 w-24 bg-surface-elevated rounded" />
              </div>
            ))}
          </div>
        )}

        {/* Error State */}
        {!loading && error && (
          <div className="max-w-xl mx-auto py-8">
            <ErrorState error={error} onRetry={loadCandidates} />
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && candidates.length === 0 && (
          <EmptyState
            icon={Sparkles}
            title="No workflows discovered yet"
            description="WorkFlowOS needs more activity before it can identify repeated workflows."
            actionText="Run Discovery Engine"
            onAction={handleRunDiscovery}
          />
        )}

        {/* 2-Column Responsive Card Grid */}
        {!loading && !error && candidates.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {candidates.map((candidate) => (
              <CandidateCard
                key={candidate.candidate_id}
                candidate={candidate}
                onSelect={(cand) => setSelectedCandidate(cand)}
              />
            ))}
          </div>
        )}
      </section>

      {/* 4. Candidate Detail Inspector Modal */}
      {selectedCandidate && (
        <CandidateDetailModal
          candidate={selectedCandidate}
          onClose={() => setSelectedCandidate(null)}
        />
      )}
    </div>
  );
}
