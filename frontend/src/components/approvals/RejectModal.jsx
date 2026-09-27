import React, { useState } from 'react';
import { XCircle, X, AlertTriangle, ShieldAlert } from 'lucide-react';

export function RejectModal({ workflow, onClose, onConfirm, loading, apiError }) {
  if (!workflow) return null;

  const [reviewerId, setReviewerId] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [reviewerNotes, setReviewerNotes] = useState('');
  const [validationErrors, setValidationErrors] = useState({});

  const handleSubmit = (e) => {
    e.preventDefault();
    const errors = {};
    if (!reviewerId.trim()) {
      errors.reviewerId = 'Reviewer ID is required.';
    }
    if (!rejectionReason.trim()) {
      errors.rejectionReason = 'Rejection reason is required.';
    }

    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors);
      return;
    }

    setValidationErrors({});
    onConfirm({
      reviewer_id: reviewerId.trim(),
      rejection_reason: rejectionReason.trim(),
      reviewer_notes: reviewerNotes.trim() || undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/75 backdrop-blur-md animate-fadeIn">
      <div className="glass-panel w-full max-w-lg rounded-3xl border border-surface-border shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-6 border-b border-surface-border/80 flex items-start justify-between gap-4 bg-surface/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-rose-950/60 border border-rose-800/50 flex items-center justify-center text-rose-400 shrink-0">
              <XCircle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white tracking-tight">Reject workflow?</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Provide a reason for rejecting this generated workflow.
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            disabled={loading}
            className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-surface-elevated transition-colors shrink-0 disabled:opacity-50"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Target Workflow Summary */}
          <div className="p-3.5 rounded-xl bg-surface/80 border border-surface-border">
            <span className="text-2xs font-mono uppercase tracking-wider text-slate-500 block">Workflow Target</span>
            <p className="text-sm font-semibold text-white mt-0.5">{workflow.name}</p>
            <span className="text-2xs font-mono text-slate-400 mt-1 block">ID: {workflow.workflow_id}</span>
          </div>

          {/* API Error Callout */}
          {apiError && (
            <div className="p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/50 flex items-start gap-2.5 text-xs text-rose-200">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="flex-1 leading-relaxed">
                <span className="font-semibold block">Unable to reject workflow.</span>
                <span>{apiError}</span>
              </div>
            </div>
          )}

          {/* Reviewer ID Field */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
              <span>Reviewer ID <span className="text-rose-400">*</span></span>
              <span className="text-2xs font-mono text-slate-500 font-normal">Operator username or email</span>
            </label>
            <input
              type="text"
              value={reviewerId}
              onChange={(e) => {
                setReviewerId(e.target.value);
                if (validationErrors.reviewerId) {
                  setValidationErrors((prev) => ({ ...prev, reviewerId: null }));
                }
              }}
              placeholder="e.g. dev_reviewer, security_officer"
              disabled={loading}
              className={`w-full px-3.5 py-2.5 rounded-xl bg-surface border text-xs text-slate-100 placeholder-slate-600 focus:outline-none transition-colors ${
                validationErrors.reviewerId
                  ? 'border-rose-500 focus:border-rose-400'
                  : 'border-surface-border focus:border-rose-500'
              }`}
              autoFocus
            />
            {validationErrors.reviewerId && (
              <p className="text-xs text-rose-400 font-medium">{validationErrors.reviewerId}</p>
            )}
          </div>

          {/* Rejection Reason Field (Required) */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
              <span>Rejection reason <span className="text-rose-400">*</span></span>
              <span className="text-2xs font-mono text-slate-500 font-normal">Required rationale</span>
            </label>
            <textarea
              value={rejectionReason}
              onChange={(e) => {
                setRejectionReason(e.target.value);
                if (validationErrors.rejectionReason) {
                  setValidationErrors((prev) => ({ ...prev, rejectionReason: null }));
                }
              }}
              placeholder="e.g., Redundant workflow; contains duplicate CRM updates; does not meet internal security requirements."
              disabled={loading}
              rows={3}
              className={`w-full p-3 rounded-xl bg-surface border text-xs text-slate-100 placeholder-slate-600 focus:outline-none transition-colors resize-none ${
                validationErrors.rejectionReason
                  ? 'border-rose-500 focus:border-rose-400'
                  : 'border-surface-border focus:border-rose-500'
              }`}
            />
            {validationErrors.rejectionReason && (
              <p className="text-xs text-rose-400 font-medium">{validationErrors.rejectionReason}</p>
            )}
          </div>

          {/* Reviewer Notes Field (Optional) */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
              <span>Reviewer notes <span className="text-2xs text-slate-500 font-normal">(optional)</span></span>
              <span className="text-2xs font-mono text-slate-500 font-normal">Additional notes</span>
            </label>
            <input
              type="text"
              value={reviewerNotes}
              onChange={(e) => setReviewerNotes(e.target.value)}
              placeholder="e.g. Consult team lead before re-generating."
              disabled={loading}
              className="w-full px-3.5 py-2.5 rounded-xl bg-surface border border-surface-border text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-rose-500 transition-colors"
            />
          </div>

          {/* Warning Notice */}
          <div className="p-3 rounded-xl bg-rose-950/20 border border-rose-900/40 text-2xs text-rose-300 flex items-start gap-2">
            <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <span>
              Rejecting permanently moves this workflow to <code className="font-mono text-white">rejected</code> status. 
              The rejection reason will be stored with the audit log.
            </span>
          </div>

          {/* Buttons */}
          <div className="pt-3 border-t border-surface-border flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 text-xs font-medium rounded-xl text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2.5 text-xs font-semibold rounded-xl bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white shadow-lg shadow-rose-600/20 transition-all flex items-center gap-2"
            >
              <XCircle className="w-3.5 h-3.5" />
              <span>{loading ? 'Rejecting...' : 'Reject workflow'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
