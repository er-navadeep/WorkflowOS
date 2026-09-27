import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  GitBranch, 
  Filter, 
  Sparkles, 
  Layers, 
  CheckCircle2, 
  Clock, 
  XCircle, 
  Info,
  RefreshCw
} from 'lucide-react';
import { api } from '../../services/api/client';
import { WorkflowDefinitionCard } from '../../components/workflows/WorkflowDefinitionCard';
import { ErrorState, EmptyState } from '../../components/common/FeedbackStates';

export function WorkflowsPage() {
  const navigate = useNavigate();

  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');

  useEffect(() => {
    loadWorkflows();
  }, []);

  async function loadWorkflows() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listWorkflows();
      setWorkflows(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load workflows:', err);
      setError(new Error("Unable to load workflows."));
    } finally {
      setLoading(false);
    }
  }

  // Summary metrics calculated strictly from real backend workflow definitions
  const totalCount = workflows.length;
  const generatedCount = workflows.filter((w) => w.status === 'generated').length;
  const approvedCount = workflows.filter((w) => w.status === 'approved').length;
  const rejectedCount = workflows.filter((w) => w.status === 'rejected').length;

  // Filter client-side
  const filteredWorkflows = workflows.filter((w) => {
    if (statusFilter === 'all') return true;
    return w.status === statusFilter;
  });

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* 1. Page Header & Explanatory Section */}
      <section className="space-y-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Workflows
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            AI-generated workflow definitions created from discovered patterns.
          </p>
        </div>

        {/* Informational Callout */}
        <div className="p-4 rounded-2xl glass-panel border border-surface-border flex items-start gap-3">
          <div className="p-2 rounded-xl bg-primary-950/60 border border-primary-800/50 text-primary-400 shrink-0 mt-0.5">
            <Info className="w-4 h-4" />
          </div>
          <div className="text-xs text-slate-300 leading-relaxed flex-1">
            <span className="font-semibold text-white block">Workflow Definition Catalog</span>
            These workflows are generated from observed activity and are waiting for human review before automation.
            Definitions represent structured execution specifications and do not execute automated actions without operator approval.
          </div>
          <button
            onClick={loadWorkflows}
            disabled={loading}
            className="hidden sm:inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-xl bg-surface-elevated hover:bg-slate-700 text-slate-300 border border-surface-border transition-all shrink-0"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </section>

      {/* 2. Summary Metrics Section */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Workflows */}
        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Total Workflows</span>
            <div className="p-2 rounded-xl bg-primary-950/40 border border-primary-800/50 text-primary-400">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-white font-mono">
              {loading ? '—' : totalCount}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Synthesized definitions</p>
          </div>
        </div>

        {/* Generated */}
        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Generated</span>
            <div className="p-2 rounded-xl bg-amber-950/40 border border-amber-800/50 text-amber-400">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-amber-400 font-mono">
              {loading ? '—' : generatedCount}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Pending human review</p>
          </div>
        </div>

        {/* Approved */}
        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Approved</span>
            <div className="p-2 rounded-xl bg-emerald-950/40 border border-emerald-800/50 text-emerald-400">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-emerald-400 font-mono">
              {loading ? '—' : approvedCount}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Signed off for automation</p>
          </div>
        </div>

        {/* Rejected */}
        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Rejected</span>
            <div className="p-2 rounded-xl bg-rose-950/40 border border-rose-800/50 text-rose-400">
              <XCircle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-rose-400 font-mono">
              {loading ? '—' : rejectedCount}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Declined definitions</p>
          </div>
        </div>
      </section>

      {/* 3. Filter Bar & List Header */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-3 rounded-2xl glass-panel border border-surface-border">
          {/* Status Filter Buttons */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <div className="flex items-center gap-1.5 text-xs font-medium text-slate-400 mr-2 px-1">
              <Filter className="w-3.5 h-3.5" />
              <span>Status:</span>
            </div>

            {[
              { id: 'all', label: 'All', count: totalCount },
              { id: 'generated', label: 'Generated', count: generatedCount },
              { id: 'approved', label: 'Approved', count: approvedCount },
              { id: 'rejected', label: 'Rejected', count: rejectedCount },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all flex items-center gap-1.5 ${
                  statusFilter === tab.id
                    ? 'bg-primary-600 text-white shadow-md shadow-primary-600/30 font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-surface-elevated'
                }`}
              >
                <span>{tab.label}</span>
                <span className={`text-2xs font-mono px-1.5 py-0.2 rounded-full ${
                  statusFilter === tab.id ? 'bg-primary-700/80 text-white' : 'bg-surface text-slate-500'
                }`}>
                  {loading ? '—' : tab.count}
                </span>
              </button>
            ))}
          </div>

          <span className="text-2xs font-mono text-slate-400 self-end sm:self-center pr-2">
            Showing {filteredWorkflows.length} of {workflows.length} workflows
          </span>
        </div>

        {/* Loading State with Skeleton Cards */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-pulse">
            {[1, 2].map((i) => (
              <div key={i} className="glass-card rounded-2xl p-6 h-72 flex flex-col justify-between">
                <div className="space-y-3">
                  <div className="h-4 w-28 bg-surface-elevated rounded" />
                  <div className="h-6 w-52 bg-surface-elevated rounded" />
                  <div className="h-3 w-full bg-surface-elevated rounded" />
                  <div className="h-3 w-3/4 bg-surface-elevated rounded" />
                </div>
                <div className="h-14 w-full bg-surface-elevated/40 rounded-xl" />
                <div className="h-4 w-32 bg-surface-elevated rounded" />
              </div>
            ))}
          </div>
        )}

        {/* Error State */}
        {!loading && error && (
          <div className="max-w-xl mx-auto py-8">
            <ErrorState error={error} onRetry={loadWorkflows} />
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && filteredWorkflows.length === 0 && (
          <EmptyState
            icon={GitBranch}
            title={workflows.length === 0 ? "No workflows generated yet" : "No workflows match filter"}
            description={
              workflows.length === 0
                ? "WorkFlowOS has not generated any workflow definitions from discovered activity."
                : `No workflow definitions found with status '${statusFilter}'.`
            }
          />
        )}

        {/* 2-Column Responsive Card Grid */}
        {!loading && !error && filteredWorkflows.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {filteredWorkflows.map((workflow) => (
              <WorkflowDefinitionCard
                key={workflow.workflow_id}
                workflow={workflow}
                onSelect={(wf) => navigate(`/workflows/${wf.workflow_id}`)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
