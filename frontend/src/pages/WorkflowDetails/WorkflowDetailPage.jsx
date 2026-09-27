import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { 
  ArrowLeft, 
  GitBranch, 
  Sparkles, 
  ShieldCheck, 
  Clock, 
  CheckCircle2, 
  XCircle, 
  AlertTriangle,
  Cpu, 
  Calendar, 
  Layers, 
  Zap, 
  Sliders, 
  Variable, 
  Database,
  Info,
  Play,
  ArrowRight,
  History
} from 'lucide-react';
import { api } from '../../services/api/client';
import { 
  WorkflowStatusBadge, 
  WorkflowTrigger, 
  WorkflowStepList, 
  WorkflowCondition,
  WorkflowVariablesList,
  WorkflowIntegrationsList,
  WorkflowErrorHandlingSection,
  IntegrationBadge
} from '../../components/workflows/WorkflowComponents';
import { LoadingState, ErrorState } from '../../components/common/FeedbackStates';
import { DryRunConfirmModal } from '../../components/executions/DryRunConfirmModal';
import { LiveExecutionConfirmModal } from '../../components/executions/LiveExecutionConfirmModal';
import { ExecutionDetailModal } from '../../components/executions/ExecutionDetailModal';
import { ExecutionHistorySection } from '../../components/executions/ExecutionHistorySection';
import { TriggerControlCard } from '../../components/triggers/TriggerControlCard';

export function WorkflowDetailPage() {
  const { workflowId } = useParams();
  const navigate = useNavigate();

  const [workflow, setWorkflow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Executions state
  const [executions, setExecutions] = useState([]);
  const [loadingExecutions, setLoadingExecutions] = useState(false);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [liveConfirmModalOpen, setLiveConfirmModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [selectedExecution, setSelectedExecution] = useState(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionError, setExecutionError] = useState(null);

  useEffect(() => {
    loadWorkflow();
    loadExecutions();
  }, [workflowId]);

  async function loadWorkflow() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getWorkflow(workflowId);
      setWorkflow(data);
    } catch (err) {
      console.error('Failed to load workflow definition:', err);
      // Fallback: check listWorkflows if direct getWorkflow errors
      try {
        const list = await api.listWorkflows();
        const found = list.find(w => w.workflow_id === workflowId);
        if (found) {
          setWorkflow(found);
          return;
        }
      } catch {
        // ignore fallback error
      }
      setError(new Error("Unable to load workflow definition details."));
    } finally {
      setLoading(false);
    }
  }

  async function loadExecutions() {
    if (!workflowId) return;
    setLoadingExecutions(true);
    try {
      const data = await api.listWorkflowExecutions(workflowId);
      if (Array.isArray(data)) {
        setExecutions(data);
      }
    } catch (err) {
      console.error('Failed to load execution history:', err);
    } finally {
      setLoadingExecutions(false);
    }
  }

  async function handleStartDryRun() {
    if (!workflow || workflow.status !== 'approved') return;

    setIsExecuting(true);
    setExecutionError(null);

    try {
      const response = await api.startDryRun(workflow.workflow_id);
      const executionRecord = response.execution || response;

      // Close confirmation modal, open detail view with results
      setConfirmModalOpen(false);
      setSelectedExecution(executionRecord);
      setDetailModalOpen(true);

      // Refresh execution history
      await loadExecutions();
    } catch (err) {
      console.error('Dry-run execution failed:', err);
      let friendlyMsg = 'Unable to connect to the execution service.';
      if (err.status === 409) {
        friendlyMsg = 'This workflow is not approved for execution.';
      } else if (err.status === 404) {
        friendlyMsg = 'Workflow or execution not found.';
      } else if (err.status === 422) {
        friendlyMsg = 'The workflow definition cannot be simulated.';
      } else if (err.message) {
        friendlyMsg = err.message;
      }
      setExecutionError(new Error(friendlyMsg));
    } finally {
      setIsExecuting(false);
    }
  }

  async function handleStartLiveExecution(customVariables = {}) {
    if (!workflow || workflow.status !== 'approved') return;

    setIsExecuting(true);
    setExecutionError(null);

    try {
      const payload = { variables: customVariables };
      const response = await api.startLiveExecution(workflow.workflow_id, payload);
      const executionRecord = response.execution || response;

      // Close live modal, open detail view with results
      setLiveConfirmModalOpen(false);
      setSelectedExecution(executionRecord);
      setDetailModalOpen(true);

      // Refresh execution history
      await loadExecutions();
    } catch (err) {
      console.error('Live execution failed:', err);
      let friendlyMsg = 'Unable to connect to the execution service.';
      if (err.status === 409) {
        friendlyMsg = 'This workflow is not approved for live execution.';
      } else if (err.status === 404) {
        friendlyMsg = 'Workflow or execution not found.';
      } else if (err.status === 422) {
        friendlyMsg = 'The workflow definition cannot be executed live.';
      } else if (err.message) {
        friendlyMsg = err.message;
      }
      setExecutionError(new Error(friendlyMsg));
    } finally {
      setIsExecuting(false);
    }
  }

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto py-12">
        <LoadingState message="Loading workflow specification..." />
      </div>
    );
  }

  if (error || !workflow) {
    return (
      <div className="max-w-xl mx-auto py-12 space-y-4">
        <Link 
          to="/workflows"
          className="inline-flex items-center gap-2 text-xs font-semibold text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Workflows</span>
        </Link>
        <ErrorState 
          error={error || new Error("Workflow not found.")} 
          onRetry={loadWorkflow} 
        />
      </div>
    );
  }

  const confidencePct = typeof workflow.generation_confidence === 'number'
    ? `${(workflow.generation_confidence * 100).toFixed(0)}%`
    : '—';

  const createdDate = workflow.created_at
    ? new Date(workflow.created_at).toLocaleString('en-US', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : '—';

  // Lifecycle status text according to Approval Separation
  const statusLifecycleMessages = {
    generated: {
      text: 'Waiting for human approval',
      description: 'This workflow has been generated from discovered activity and is waiting for human review before automation.',
      classes: 'bg-amber-950/40 border-amber-800/50 text-amber-300',
      icon: Clock,
    },
    approved: {
      text: 'Approved — eligible for safe simulation',
      description: 'This workflow has been reviewed and approved by an operator. It is eligible for dry-run simulation.',
      classes: 'bg-emerald-950/40 border-emerald-800/50 text-emerald-300',
      icon: CheckCircle2,
    },
    rejected: {
      text: 'Rejected',
      description: 'This workflow was rejected during review and will not be automated.',
      classes: 'bg-rose-950/40 border-rose-800/50 text-rose-300',
      icon: XCircle,
    },
  };

  const lifecycleMeta = statusLifecycleMessages[workflow.status] || {
    text: workflow.status,
    description: 'Current status in lifecycle.',
    classes: 'bg-slate-800/40 border-slate-700 text-slate-300',
    icon: Info,
  };
  const LifecycleIcon = lifecycleMeta.icon;

  const isApproved = workflow.status === 'approved';
  const isGenerated = workflow.status === 'generated';
  const isRejected = workflow.status === 'rejected';

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-12">
      {/* Top Breadcrumb & Back Action */}
      <div className="flex items-center justify-between gap-4">
        <Link 
          to="/workflows"
          className="inline-flex items-center gap-2 text-xs font-semibold text-slate-400 hover:text-white transition-colors group"
        >
          <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
          <span>Back to Workflows</span>
        </Link>

        <div className="flex items-center gap-2 text-2xs font-mono text-slate-500">
          <span>Workflow ID:</span>
          <span className="text-slate-300 bg-surface px-2 py-0.5 rounded border border-surface-border truncate max-w-[200px]">
            {workflow.workflow_id}
          </span>
        </div>
      </div>

      {/* Trust & Safety Warning Banner */}
      <div className="p-4 rounded-2xl bg-cyan-950/30 border border-cyan-800/50 flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
        <div className="text-xs leading-relaxed">
          <span className="font-semibold text-cyan-300 uppercase tracking-wider block font-mono text-2xs">
            WorkFlowOS Trust & Security Notice
          </span>
          <p className="text-slate-300 mt-1">
            This is a display-only workflow specification. 
            No credentials, API keys, passwords, or OAuth tokens are stored in this definition. 
            Execution is strictly gated behind human approval. Dry-run performs pure safe simulation.
          </p>
        </div>
      </div>

      {/* A. Workflow Overview Card */}
      <section className="glass-panel rounded-3xl p-6 sm:p-8 space-y-6 border border-surface-border shadow-xl">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-surface-border/80 pb-6">
          <div className="space-y-1">
            <span className="text-2xs font-mono uppercase tracking-widest text-primary-400 font-semibold flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5" />
              AI-Generated Workflow Definition
            </span>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              {workflow.name}
            </h1>
          </div>

          <div className="flex items-center gap-3">
            <WorkflowStatusBadge status={workflow.status} />
          </div>
        </div>

        {/* Phase 8.2 & 8.3 Execution Action Banner (Strict Approval Guard) */}
        {isApproved && (
          <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-700/60 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-bold text-white font-mono uppercase tracking-wider">
                  Approved & Automation Ready
                </span>
              </div>
              <p className="text-xs text-slate-300">
                Execute safely in simulated dry-run mode or live with real external integrations (Slack).
              </p>
            </div>

            <div className="flex items-center gap-2.5 shrink-0">
              <button
                type="button"
                onClick={() => {
                  setExecutionError(null);
                  setConfirmModalOpen(true);
                }}
                className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-bold text-cyan-300 bg-cyan-950/70 hover:bg-cyan-900/80 border border-cyan-700/60 shadow-md transition-all shrink-0 cursor-pointer"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Run Dry Run</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setExecutionError(null);
                  setLiveConfirmModalOpen(true);
                }}
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-600/30 transition-all shrink-0 cursor-pointer"
              >
                <Zap className="w-3.5 h-3.5 fill-current" />
                <span>Execute Live</span>
              </button>
            </div>
          </div>
        )}

        {isGenerated && (
          <div className="p-4 rounded-2xl bg-amber-950/30 border border-amber-800/50 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-0.5">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-amber-400" />
                <span className="text-xs font-bold text-amber-300 font-mono uppercase tracking-wider">
                  Approval Guard Active
                </span>
              </div>
              <p className="text-xs text-slate-300">
                Human approval required before execution.
              </p>
            </div>

            <Link
              to="/approvals"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-amber-300 bg-amber-950/60 hover:bg-amber-900/60 border border-amber-700/60 transition-colors shrink-0"
            >
              <span>Review in Approval Queue</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        )}

        {isRejected && (
          <div className="p-4 rounded-2xl bg-rose-950/30 border border-rose-800/50 flex items-center gap-3">
            <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <div className="text-xs">
              <span className="font-bold text-rose-300 uppercase tracking-wider font-mono text-2xs block">
                Execution Disabled
              </span>
              <p className="text-slate-300 mt-0.5">
                Not available until approved. This workflow was rejected during review.
              </p>
            </div>
          </div>
        )}

        {/* Informational Lifecycle Callout */}
        <div className={`p-4 rounded-2xl border flex items-start gap-3 ${lifecycleMeta.classes}`}>
          <LifecycleIcon className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="text-xs leading-relaxed">
            <span className="font-bold text-sm block">{lifecycleMeta.text}</span>
            <p className="opacity-90 mt-0.5">{lifecycleMeta.description}</p>
            {workflow.reviewer_notes && (
              <p className="mt-2 text-2xs font-mono opacity-80 pt-2 border-t border-current/20">
                Reviewer note: "{workflow.reviewer_notes}"
              </p>
            )}
          </div>
        </div>

        {/* Description */}
        <div>
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider font-mono text-2xs mb-1.5">
            Overview
          </h2>
          <p className="text-sm text-slate-200 leading-relaxed">
            {workflow.description}
          </p>
        </div>

        {/* Key Metadata Stats Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
          <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
            <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Confidence</span>
            <span className="text-lg font-bold text-cyan-400 font-mono mt-0.5 block">{confidencePct}</span>
            <span className="text-2xs text-slate-500 mt-0.5 block">AI understanding match</span>
          </div>

          <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
            <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Business Actions</span>
            <span className="text-lg font-bold text-white font-mono mt-0.5 block">
              {workflow.steps?.length === 6 ? '5 Actions' : (workflow.steps?.length || 0)}
            </span>
            <span className="text-2xs text-slate-500 mt-0.5 block">
              {workflow.steps?.length === 6 ? '6 technical steps' : 'Sequential operations'}
            </span>
          </div>

          <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
            <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">AI Model</span>
            <span className="text-xs font-bold text-indigo-300 font-mono mt-1.5 block truncate">
              {workflow.model_used || 'Gemini'}
            </span>
            <span className="text-2xs text-slate-500 mt-0.5 block">Generation engine</span>
          </div>

          <div className="p-3.5 rounded-xl bg-surface/70 border border-surface-border">
            <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Created</span>
            <span className="text-2xs font-bold text-slate-300 font-mono mt-1.5 block truncate">
              {createdDate}
            </span>
            <span className="text-2xs text-slate-500 mt-0.5 block">Initial synthesis</span>
          </div>
        </div>
      </section>

      {/* Automation Trigger Controls (Phase 8.11 Master Automation Layer) */}
      <TriggerControlCard
        workflow={workflow}
        onTriggerUpdated={() => {
          loadWorkflow();
          loadExecutions();
        }}
      />

      {/* Execution History Section */}
      <ExecutionHistorySection
        executions={executions}
        loading={loadingExecutions}
        onRefresh={loadExecutions}
        onSelectExecution={(exec) => {
          setSelectedExecution(exec);
          setDetailModalOpen(true);
        }}
      />

      {/* B. Trigger Section */}
      <section className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4 border border-surface-border">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-primary-400" />
          <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
            Trigger Definition
          </h2>
        </div>

        {workflow.trigger ? (
          <WorkflowTrigger trigger={workflow.trigger} />
        ) : (
          <p className="text-xs text-slate-500 italic">No trigger definition specified.</p>
        )}
      </section>

      {/* C. Execution Steps Pipeline */}
      <section className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4 border border-surface-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              Action Pipeline (5 Business Actions / 6 Technical Steps)
            </h2>
          </div>
          <span className="text-2xs font-mono text-slate-400">
            {workflow.steps?.length === 6 ? '5 business actions (6 technical steps)' : `${workflow.steps?.length || 0} sequential steps`}
          </span>
        </div>

        <WorkflowStepList steps={workflow.steps} showDetails={true} />
      </section>

      {/* D. Conditions Section */}
      <section className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4 border border-surface-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              Conditions
            </h2>
          </div>
          <span className="text-2xs font-mono text-slate-400">
            {workflow.conditions?.length || 0} guard{workflow.conditions?.length === 1 ? '' : 's'}
          </span>
        </div>

        {workflow.conditions && workflow.conditions.length > 0 ? (
          <div className="space-y-3">
            {workflow.conditions.map((cond, i) => (
              <WorkflowCondition key={cond.condition_id || i} condition={cond} />
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-500 italic p-3 rounded-xl bg-surface/40 border border-surface-border">
            No conditional branching defined for this workflow.
          </p>
        )}
      </section>

      {/* E. Variables Section */}
      <section className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4 border border-surface-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Variable className="w-4 h-4 text-indigo-400" />
            <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              Workflow Variables
            </h2>
          </div>
          <span className="text-2xs font-mono text-slate-400">
            {workflow.variables?.length || 0} data variable{workflow.variables?.length === 1 ? '' : 's'}
          </span>
        </div>

        <WorkflowVariablesList variables={workflow.variables} />
      </section>

      {/* F. Integrations Section */}
      <section className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4 border border-surface-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              Integrations Required
            </h2>
          </div>
          <span className="text-2xs font-mono text-slate-400">
            {workflow.integrations?.length || 0} application{workflow.integrations?.length === 1 ? '' : 's'}
          </span>
        </div>

        <WorkflowIntegrationsList integrations={workflow.integrations} />
      </section>

      {/* G. Error Handling Policy Section */}
      <section className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4 border border-surface-border">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
            Error Handling Policy
          </h2>
        </div>

        <WorkflowErrorHandlingSection errorHandling={workflow.error_handling} />
      </section>

      {/* Footer Navigation Back to Catalog */}
      <div className="pt-4 flex items-center justify-between border-t border-surface-border">
        <Link 
          to="/workflows"
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-surface-elevated hover:bg-slate-700 text-xs font-semibold text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to All Workflows</span>
        </Link>

        <span className="text-2xs font-mono text-slate-500">
          Source Understanding ID: {workflow.understanding_id?.slice(0, 16)}...
        </span>
      </div>

      {/* Confirmation Modal */}
      <DryRunConfirmModal
        isOpen={confirmModalOpen}
        onClose={() => {
          if (!isExecuting) {
            setConfirmModalOpen(false);
            setExecutionError(null);
          }
        }}
        onConfirm={handleStartDryRun}
        workflow={workflow}
        isExecuting={isExecuting}
        error={executionError}
      />

      {/* Live Execution Confirmation Modal */}
      <LiveExecutionConfirmModal
        isOpen={liveConfirmModalOpen}
        onClose={() => {
          if (!isExecuting) {
            setLiveConfirmModalOpen(false);
            setExecutionError(null);
          }
        }}
        onConfirm={handleStartLiveExecution}
        workflow={workflow}
        isExecuting={isExecuting}
        error={executionError}
      />

      {/* Detail Modal */}
      <ExecutionDetailModal
        isOpen={detailModalOpen}
        onClose={() => {
          setDetailModalOpen(false);
          setSelectedExecution(null);
        }}
        execution={selectedExecution}
      />
    </div>
  );
}
