import React, { useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { 
  CheckSquare, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Sparkles, 
  ShieldAlert, 
  ShieldCheck,
  RefreshCw, 
  ArrowRight,
  Info,
  Layers,
  History,
  AlertTriangle
} from 'lucide-react';
import { api } from '../../services/api/client';
import { PendingWorkflowCard } from '../../components/approvals/PendingWorkflowCard';
import { ApproveModal } from '../../components/approvals/ApproveModal';
import { RejectModal } from '../../components/approvals/RejectModal';
import { ReviewWorkflowModal } from '../../components/approvals/ReviewWorkflowModal';
import { WorkflowStatusBadge, IntegrationBadge } from '../../components/workflows/WorkflowComponents';
import { ErrorState, EmptyState } from '../../components/common/FeedbackStates';

export function ApprovalsPage() {
  const { setPendingCount } = useOutletContext() || {};

  const [pendingWorkflows, setPendingWorkflows] = useState([]);
  const [reviewedWorkflows, setReviewedWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Active modal targets
  const [reviewingWorkflow, setReviewingWorkflow] = useState(null);
  const [approvingWorkflow, setApprovingWorkflow] = useState(null);
  const [rejectingWorkflow, setRejectingWorkflow] = useState(null);

  // Modal execution & error states
  const [modalLoading, setModalLoading] = useState(false);
  const [approveError, setApproveError] = useState(null);
  const [rejectError, setRejectError] = useState(null);

  // Success notification
  const [successNotice, setSuccessNotice] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch pending workflows
      const pendingData = await api.getPendingWorkflows();
      const pendingList = Array.isArray(pendingData) ? pendingData : [];
      setPendingWorkflows(pendingList);
      if (setPendingCount) setPendingCount(pendingList.length);

      // 2. Fetch reviewed history from general workflows catalog
      try {
        const allData = await api.listWorkflows();
        if (Array.isArray(allData)) {
          const reviewed = allData
            .filter((w) => w.status === 'approved' || w.status === 'rejected')
            .sort((a, b) => new Date(b.updated_at || b.approved_at || b.rejected_at || b.created_at) - new Date(a.updated_at || a.approved_at || a.rejected_at || a.created_at));
          setReviewedWorkflows(reviewed.slice(0, 5));
        }
      } catch (err) {
        console.warn('Could not load reviewed history:', err);
      }
    } catch (err) {
      console.error('Failed to load pending workflows:', err);
      setError(new Error("Unable to load pending approval queue."));
    } finally {
      setLoading(false);
    }
  }

  // Handle Approve Confirmation
  async function handleConfirmApprove(payload) {
    if (!approvingWorkflow) return;
    setModalLoading(true);
    setApproveError(null);

    try {
      await api.approveWorkflow(approvingWorkflow.workflow_id, payload);

      // Update local state cleanly
      const approvedWf = approvingWorkflow;
      setPendingWorkflows((prev) => {
        const nextList = prev.filter((w) => w.workflow_id !== approvedWf.workflow_id);
        if (setPendingCount) setPendingCount(nextList.length);
        return nextList;
      });

      setSuccessNotice(`Workflow "${approvedWf.name}" approved successfully.`);
      setApprovingWorkflow(null);
      setReviewingWorkflow(null);

      // Refresh history in background
      loadData();
    } catch (err) {
      console.error('Approve error:', err);
      if (err.status === 409 || err.message?.includes('409') || err.message?.includes('status')) {
        setApproveError(
          "This workflow is no longer awaiting review. Refreshing the approval queue..."
        );
        setTimeout(() => {
          setApprovingWorkflow(null);
          loadData();
        }, 2000);
      } else {
        setApproveError(err.message || "Unable to approve workflow. Please retry.");
      }
    } finally {
      setModalLoading(false);
    }
  }

  // Handle Reject Confirmation
  async function handleConfirmReject(payload) {
    if (!rejectingWorkflow) return;
    setModalLoading(true);
    setRejectError(null);

    try {
      await api.rejectWorkflow(rejectingWorkflow.workflow_id, payload);

      // Update local state cleanly
      const rejectedWf = rejectingWorkflow;
      setPendingWorkflows((prev) => {
        const nextList = prev.filter((w) => w.workflow_id !== rejectedWf.workflow_id);
        if (setPendingCount) setPendingCount(nextList.length);
        return nextList;
      });

      setSuccessNotice(`Workflow "${rejectedWf.name}" rejected successfully.`);
      setRejectingWorkflow(null);
      setReviewingWorkflow(null);

      // Refresh history in background
      loadData();
    } catch (err) {
      console.error('Reject error:', err);
      if (err.status === 409 || err.message?.includes('409') || err.message?.includes('status')) {
        setRejectError(
          "This workflow is no longer awaiting review. Refreshing the approval queue..."
        );
        setTimeout(() => {
          setRejectingWorkflow(null);
          loadData();
        }, 2000);
      } else {
        setRejectError(err.message || "Unable to reject workflow. Please retry.");
      }
    } finally {
      setModalLoading(false);
    }
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* 1. Page Header & Informational Banner */}
      <section className="space-y-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Approval Queue
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Review AI-generated workflows before they become eligible for automation.
          </p>
        </div>

        {/* Informational Banner */}
        <div className="p-4 rounded-2xl glass-panel border border-surface-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-amber-950/60 border border-amber-800/50 text-amber-400 shrink-0 mt-0.5 sm:mt-0">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div className="text-xs text-slate-300 leading-relaxed">
              <span className="font-semibold text-white block">Human-in-the-Loop Governance Gate</span>
              WorkFlowOS requires human approval before a generated workflow can proceed toward automation.
              <div className="flex items-center gap-2 mt-1.5 font-mono text-2xs text-slate-400">
                <span className="text-amber-400 font-bold">Generated</span>
                <span>→</span>
                <span className="text-cyan-400 font-bold">Human Review</span>
                <span>→</span>
                <span className="text-emerald-400 font-bold">Approved</span>
                <span>/</span>
                <span className="text-rose-400 font-bold">Rejected</span>
              </div>
            </div>
          </div>

          <button
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-xl bg-surface-elevated hover:bg-slate-700 text-slate-300 border border-surface-border transition-all shrink-0 self-end sm:self-center"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh Queue</span>
          </button>
        </div>
      </section>

      {/* Success Notification Alert */}
      {successNotice && (
        <div className="p-4 rounded-2xl bg-emerald-950/40 border border-emerald-800/50 flex items-center justify-between gap-3 text-xs text-emerald-200 animate-fadeIn">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="font-semibold">{successNotice}</span>
          </div>
          <button
            onClick={() => setSuccessNotice(null)}
            className="text-xs text-emerald-400 hover:text-white font-semibold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 2. Pending Workflows Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              Workflows Awaiting Review
            </h2>
          </div>
          <span className="text-2xs font-mono text-slate-400">
            {pendingWorkflows.length} item{pendingWorkflows.length === 1 ? '' : 's'} pending
          </span>
        </div>

        {/* Loading State with Skeleton Cards */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-pulse">
            {[1, 2].map((i) => (
              <div key={i} className="glass-card rounded-2xl p-6 h-72 flex flex-col justify-between">
                <div className="space-y-3">
                  <div className="h-4 w-28 bg-surface-elevated rounded" />
                  <div className="h-6 w-48 bg-surface-elevated rounded" />
                  <div className="h-3 w-full bg-surface-elevated rounded" />
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
            <ErrorState error={error} onRetry={loadData} />
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && pendingWorkflows.length === 0 && (
          <EmptyState
            icon={CheckCircle2}
            title="No workflows awaiting approval"
            description="You're all caught up. Newly generated workflows will appear here when they need review."
          />
        )}

        {/* Pending Cards Grid */}
        {!loading && !error && pendingWorkflows.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {pendingWorkflows.map((workflow) => (
              <PendingWorkflowCard
                key={workflow.workflow_id}
                workflow={workflow}
                onView={(wf) => setReviewingWorkflow(wf)}
                onApprove={(wf) => {
                  setApproveError(null);
                  setApprovingWorkflow(wf);
                }}
                onReject={(wf) => {
                  setRejectError(null);
                  setRejectingWorkflow(wf);
                }}
              />
            ))}
          </div>
        )}
      </section>

      {/* 3. Recently Reviewed Section (Requirement 12) */}
      {!loading && reviewedWorkflows.length > 0 && (
        <section className="space-y-4 pt-6 border-t border-surface-border/80">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4 text-slate-400" />
              <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider font-mono">
                Recently Reviewed
              </h2>
            </div>
            <span className="text-2xs font-mono text-slate-500">
              Audit log record
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {reviewedWorkflows.map((wf) => (
              <div 
                key={wf.workflow_id} 
                className="p-4 rounded-2xl glass-card border border-surface-border flex flex-col justify-between space-y-3"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <h3 className="text-xs font-semibold text-white truncate flex-1">
                      {wf.name}
                    </h3>
                    <WorkflowStatusBadge status={wf.status} />
                  </div>
                  <p className="text-2xs text-slate-400 line-clamp-2 leading-relaxed">
                    {wf.description}
                  </p>
                </div>

                <div className="pt-2 border-t border-surface-border/60 text-2xs font-mono text-slate-500 space-y-1">
                  {wf.reviewed_by && (
                    <div>Reviewer: <span className="text-slate-300">{wf.reviewed_by}</span></div>
                  )}
                  {wf.reviewer_notes && (
                    <div className="truncate text-slate-400">Note: "{wf.reviewer_notes}"</div>
                  )}
                  {wf.rejection_reason && (
                    <div className="truncate text-rose-300">Reason: "{wf.rejection_reason}"</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 4. Modals */}

      {/* Full Review Modal */}
      {reviewingWorkflow && (
        <ReviewWorkflowModal
          workflow={reviewingWorkflow}
          onClose={() => setReviewingWorkflow(null)}
          onApprove={(wf) => {
            setApproveError(null);
            setApprovingWorkflow(wf);
          }}
          onReject={(wf) => {
            setRejectError(null);
            setRejectingWorkflow(wf);
          }}
        />
      )}

      {/* Approve Confirmation Modal */}
      {approvingWorkflow && (
        <ApproveModal
          workflow={approvingWorkflow}
          loading={modalLoading}
          apiError={approveError}
          onClose={() => {
            if (!modalLoading) {
              setApprovingWorkflow(null);
              setApproveError(null);
            }
          }}
          onConfirm={handleConfirmApprove}
        />
      )}

      {/* Reject Confirmation Modal */}
      {rejectingWorkflow && (
        <RejectModal
          workflow={rejectingWorkflow}
          loading={modalLoading}
          apiError={rejectError}
          onClose={() => {
            if (!modalLoading) {
              setRejectingWorkflow(null);
              setRejectError(null);
            }
          }}
          onConfirm={handleConfirmReject}
        />
      )}
    </div>
  );
}
