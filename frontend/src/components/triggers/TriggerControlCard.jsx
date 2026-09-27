import React, { useState, useEffect } from 'react';
import { 
  Zap, 
  Play, 
  Pause, 
  RefreshCw, 
  Clock, 
  ShieldAlert, 
  CheckCircle2, 
  AlertTriangle, 
  Activity, 
  TrendingUp,
  Settings2,
  Mail
} from 'lucide-react';
import { api } from '../../services/api/client';
import { IntegrationBadge } from '../workflows/WorkflowComponents';

export function TriggerControlCard({ workflow, onTriggerUpdated }) {
  const [trigger, setTrigger] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);
  const [polling, setPolling] = useState(false);
  const [pollResult, setPollResult] = useState(null);
  const [error, setError] = useState(null);

  const isApproved = workflow?.status === 'approved';

  useEffect(() => {
    if (workflow?.workflow_id) {
      loadTriggerState();
    }
  }, [workflow?.workflow_id]);

  async function loadTriggerState() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTrigger(workflow.workflow_id);
      setTrigger(data);
      try {
        const fb = await api.getWorkflowFeedback(workflow.workflow_id);
        setFeedback(fb);
      } catch {
        // feedback optional
      }
    } catch (err) {
      console.error('Failed to load trigger configuration:', err);
      setError('Unable to load automation configuration.');
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleAutomation() {
    if (!trigger || !isApproved) return;
    setToggling(true);
    setError(null);
    setPollResult(null);
    try {
      let updated;
      if (trigger.is_enabled) {
        updated = await api.disableTrigger(workflow.workflow_id);
      } else {
        updated = await api.enableTrigger(workflow.workflow_id);
      }
      setTrigger(updated);
      if (onTriggerUpdated) onTriggerUpdated(updated);
    } catch (err) {
      console.error('Error toggling automation:', err);
      setError(err.message || 'Failed to update automation status.');
    } finally {
      setToggling(false);
    }
  }

  async function handlePollNow() {
    if (!workflow?.workflow_id) return;
    setPolling(true);
    setPollResult(null);
    setError(null);
    try {
      const summary = await api.pollTrigger(workflow.workflow_id);
      setPollResult(summary);
      await loadTriggerState();
      if (onTriggerUpdated) onTriggerUpdated();
    } catch (err) {
      console.error('Error polling trigger:', err);
      setError(err.message || 'Failed to trigger polling check.');
    } finally {
      setPolling(false);
    }
  }

  if (loading) {
    return (
      <div className="card p-6 animate-pulse space-y-4">
        <div className="h-6 w-48 bg-slate-800 rounded"></div>
        <div className="h-20 bg-slate-850 rounded"></div>
      </div>
    );
  }

  return (
    <div className="card p-6 border border-surface-border bg-surface-elevated/20 space-y-6">
      {/* Header with Title and Global Switch */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-surface-border/60 pb-5">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center border shadow-sm ${
            trigger?.is_enabled
              ? 'bg-emerald-950/50 border-emerald-700/60 text-emerald-400 shadow-emerald-900/20'
              : 'bg-slate-900 border-slate-700 text-slate-400'
          }`}>
            <Zap className={`w-5 h-5 ${trigger?.is_enabled ? 'animate-pulse' : ''}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-white">Automated Triggering</h3>
              {trigger && (
                <span className={`px-2 py-0.5 rounded-full text-xs font-mono font-medium border ${
                  trigger.is_enabled
                    ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800/60'
                    : trigger.status === 'error'
                    ? 'bg-rose-950/40 text-rose-300 border-rose-800/60'
                    : 'bg-slate-800 text-slate-300 border-slate-700'
                }`}>
                  {trigger.is_enabled ? 'ACTIVE' : (trigger.status?.toUpperCase() || 'PAUSED')}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Continuous background polling and autonomous execution
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3 self-end sm:self-auto">
          {isApproved && (
            <button
              onClick={handlePollNow}
              disabled={polling || toggling}
              className="btn btn-secondary text-xs flex items-center gap-2 py-2 px-3 hover:border-primary-500/40"
              title="Perform an immediate check for incoming events"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${polling ? 'animate-spin text-primary-400' : ''}`} />
              <span>{polling ? 'Checking...' : 'Check / Poll Now'}</span>
            </button>
          )}

          {isApproved ? (
            <button
              onClick={handleToggleAutomation}
              disabled={toggling || polling}
              className={`btn text-xs font-semibold py-2 px-4 flex items-center gap-2 shadow-sm transition-all ${
                trigger?.is_enabled
                  ? 'bg-rose-950/60 hover:bg-rose-900/70 text-rose-200 border-rose-800/60 hover:border-rose-700'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-500 shadow-emerald-950/40'
              }`}
            >
              {trigger?.is_enabled ? (
                <>
                  <Pause className="w-3.5 h-3.5" />
                  <span>Pause Automation</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  <span>Enable Automation</span>
                </>
              )}
            </button>
          ) : (
            <div className="flex items-center gap-2 text-xs font-mono text-amber-400 bg-amber-950/30 border border-amber-800/50 px-3 py-1.5 rounded-lg">
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Approval Required</span>
            </div>
          )}
        </div>
      </div>

      {/* Guard Warning for Non-Approved Workflows */}
      {!isApproved && (
        <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-800/40 text-amber-300 text-xs flex items-start gap-3">
          <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block">Automation Locked</span>
            <span>
              This workflow is currently in <code>'{workflow?.status}'</code> status. Human approval is strictly required before background automation and event-driven triggering can be enabled.
            </span>
          </div>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-800/50 text-rose-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Manual Poll Result Feedback Banner */}
      {pollResult && (
        <div className="p-3.5 rounded-xl bg-primary-950/30 border border-primary-800/40 text-xs text-slate-200 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-primary-300 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-primary-400" />
              Poll Check Completed
            </span>
            <span className="text-2xs font-mono text-slate-400">
              {pollResult.events_detected} detected · {pollResult.events_dispatched} dispatched · {pollResult.events_skipped} skipped
            </span>
          </div>
          {pollResult.dispatches?.length > 0 && (
            <ul className="space-y-1 text-2xs font-mono text-slate-300 pt-1 border-t border-slate-800">
              {pollResult.dispatches.map((d, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="text-slate-500">•</span>
                  <span className="text-primary-300">{d.event_identifier}</span>
                  <span className="text-slate-400">—</span>
                  <span>{d.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Trigger Details Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-1">
        <div className="p-3 rounded-xl bg-surface/50 border border-surface-border">
          <span className="text-2xs font-semibold text-slate-400 uppercase tracking-wider block">Source App</span>
          <div className="mt-1 flex items-center gap-1.5">
            <IntegrationBadge application={trigger?.application || 'Gmail'} />
          </div>
        </div>

        <div className="p-3 rounded-xl bg-surface/50 border border-surface-border">
          <span className="text-2xs font-semibold text-slate-400 uppercase tracking-wider block">Poll Frequency</span>
          <div className="mt-1 flex items-center gap-1.5 text-sm font-semibold text-white font-mono">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>every {trigger?.poll_interval_seconds || 30}s</span>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-surface/50 border border-surface-border">
          <span className="text-2xs font-semibold text-slate-400 uppercase tracking-wider block">Last Checked</span>
          <div className="mt-1 text-xs text-slate-300 font-mono truncate" title={trigger?.last_polled_at}>
            {trigger?.last_polled_at ? new Date(trigger.last_polled_at).toLocaleTimeString() : 'Never'}
          </div>
        </div>

        <div className="p-3 rounded-xl bg-surface/50 border border-surface-border">
          <span className="text-2xs font-semibold text-slate-400 uppercase tracking-wider block">Last Triggered</span>
          <div className="mt-1 text-xs text-slate-300 font-mono truncate" title={trigger?.last_triggered_at}>
            {trigger?.last_triggered_at ? new Date(trigger.last_triggered_at).toLocaleTimeString() : 'Never'}
          </div>
        </div>
      </div>

      {/* Reliability & Feedback Metrics Bar */}
      {feedback && feedback.total_executions > 0 && (
        <div className="pt-2 border-t border-surface-border/50">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
            <span className="font-semibold text-slate-300 flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
              Reliability & Feedback Audit
            </span>
            <span className="font-mono text-emerald-400 font-medium">
              {feedback.completion_rate_pct}% Success Rate ({feedback.completed_count}/{feedback.total_executions} runs)
            </span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden flex">
            <div 
              className="bg-emerald-500 h-full" 
              style={{ width: `${feedback.completion_rate_pct}%` }} 
            />
            {feedback.failed_count > 0 && (
              <div 
                className="bg-rose-500 h-full" 
                style={{ width: `${(feedback.failed_count / feedback.total_executions) * 100}%` }} 
              />
            )}
          </div>
          <p className="text-2xs text-slate-400 mt-2 font-mono italic">
            Recommendation: {feedback.feedback_recommendation}
          </p>
        </div>
      )}
    </div>
  );
}
