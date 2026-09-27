import React, { useState } from 'react';
import { CheckCircle2, X, AlertTriangle, ShieldCheck } from 'lucide-react';

export function ApproveModal({ workflow, onClose, onConfirm, loading, apiError }) {
  if (!workflow) return null;

  const [reviewerId, setReviewerId] = useState('');
  const [reviewerNotes, setReviewerNotes] = useState('');
  const [validationError, setValidationError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!reviewerId.trim()) {
      setValidationError('Reviewer ID is required.');
      return;
    }
    setValidationError('');
    onConfirm({
      reviewer_id: reviewerId.trim(),
      reviewer_notes: reviewerNotes.trim() || undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/75 backdrop-blur-md animate-fadeIn">
      <div className="glass-panel w-full max-w-lg rounded-3xl border border-surface-border shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-6 border-b border-surface-border/80 flex items-start justify-between gap-4 bg-surface/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-emerald-950/60 border border-emerald-800/50 flex items-center justify-center text-emerald-400 shrink-0">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white tracking-tight">Approve workflow?</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                You are approving this workflow for future automation.
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
                <span className="font-semibold block">Unable to approve workflow.</span>
                <span>{apiError}</span>
              </div>
            </div>
          )}

          {/* Validation Error */}
          {validationError && (
            <div className="text-xs text-rose-400 font-medium">
              {validationError}
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
                if (validationError) setValidationError('');
              }}
              placeholder="e.g. dev_reviewer, admin@example.com"
              disabled={loading}
              className="w-full px-3.5 py-2.5 rounded-xl bg-surface border border-surface-border text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 transition-colors"
              autoFocus
            />
          </div>

          {/* Reviewer Notes Field */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
              <span>Reviewer notes <span className="text-2xs text-slate-500 font-normal">(optional)</span></span>
              <span className="text-2xs font-mono text-slate-500 font-normal">Governance sign-off notes</span>
            </label>
            <textarea
              value={reviewerNotes}
              onChange={(e) => setReviewerNotes(e.target.value)}
              placeholder="e.g., Sequence verified against customer handling protocol. Approved for Phase 8 automation."
              disabled={loading}
              rows={3}
              className="w-full p-3 rounded-xl bg-surface border border-surface-border text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 transition-colors resize-none"
            />
          </div>

          {/* Governance Notice */}
          <div className="p-3 rounded-xl bg-surface-elevated/40 border border-surface-border text-2xs text-slate-400 flex items-start gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span>
              Approving transitions this workflow from <code className="text-amber-300 font-mono">generated</code> to <code className="text-emerald-300 font-mono">approved</code>. 
              No external actions (Gmail, Slack, CRM) are executed at this time.
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
              className="px-5 py-2.5 text-xs font-semibold rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white shadow-lg shadow-emerald-600/20 transition-all flex items-center gap-2"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{loading ? 'Approving...' : 'Approve workflow'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
