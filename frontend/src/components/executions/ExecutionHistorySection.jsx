import React from 'react';
import { 
  History, 
  ArrowRight, 
  Layers, 
  ShieldCheck, 
  Clock, 
  RefreshCw,
  Zap,
  User
} from 'lucide-react';
import { ExecutionStatusBadge, ExecutionModeBadge } from './ExecutionStatusBadge';

export function ExecutionHistorySection({
  executions = [],
  loading = false,
  onRefresh,
  onSelectExecution,
}) {
  return (
    <section className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4 border border-surface-border">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
            Execution History
          </h2>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-2xs font-mono text-slate-400">
            {executions.length} run{executions.length === 1 ? '' : 's'}
          </span>
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={loading}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors disabled:opacity-50"
              title="Refresh execution history"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          )}
        </div>
      </div>

      {executions.length === 0 ? (
        <div className="p-8 rounded-2xl bg-surface/40 border border-surface-border text-center space-y-2">
          <ShieldCheck className="w-8 h-8 text-slate-600 mx-auto" />
          <p className="text-sm font-medium text-slate-300">No executions yet</p>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            This workflow has not been simulated yet. Click "Run Dry Run" above to safely simulate execution.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {executions.map((exec) => {
            const isAuto = exec.trigger_info?.source === 'automatic_trigger' || exec.idempotency_key?.startsWith('trigger:');
            const startedStr = exec.started_at
              ? new Date(exec.started_at).toLocaleString('en-US', {
                  dateStyle: 'short',
                  timeStyle: 'medium',
                })
              : '—';

            const completedStr = exec.completed_at
              ? new Date(exec.completed_at).toLocaleString('en-US', {
                  dateStyle: 'short',
                  timeStyle: 'medium',
                })
              : '—';

            return (
              <div
                key={exec.execution_id}
                onClick={() => onSelectExecution && onSelectExecution(exec)}
                className="p-4 rounded-2xl bg-surface-elevated/40 hover:bg-surface-elevated/80 border border-surface-border/80 hover:border-cyan-500/40 cursor-pointer transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 group"
              >
                <div className="space-y-1.5 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <ExecutionModeBadge mode={exec.mode} size="sm" />
                    {isAuto ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs font-mono font-semibold rounded-full bg-indigo-950/60 text-indigo-300 border border-indigo-700/60 shadow-sm" title="Triggered automatically by background trigger service">
                        <Zap className="w-2.5 h-2.5 text-indigo-400" />
                        <span>AUTOMATIC</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs font-mono font-medium rounded-full bg-slate-800/80 text-slate-400 border border-slate-700/60 shadow-sm" title="Manually dispatched execution">
                        <User className="w-2.5 h-2.5 text-slate-400" />
                        <span>MANUAL</span>
                      </span>
                    )}
                    <ExecutionStatusBadge status={exec.status} size="sm" />
                    <span className="text-2xs font-mono text-slate-400 bg-surface px-2 py-0.5 rounded border border-surface-border truncate max-w-[180px]">
                      {exec.execution_id}
                    </span>
                  </div>

                  {isAuto && (
                    <div className="flex items-center gap-1.5 text-2xs font-mono text-indigo-300/90 pt-0.5">
                      <Zap className="w-3 h-3 text-indigo-400 shrink-0" />
                      <span>
                        Trigger: {exec.trigger_info?.source_app || 'Gmail'} {exec.trigger_info?.email_subject ? `— "${exec.trigger_info.email_subject.slice(0, 45)}..."` : (exec.trigger_info?.event_identifier ? `— msg:${exec.trigger_info.event_identifier.slice(0, 16)}` : '')}
                      </span>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-slate-400 font-mono">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-500" />
                      Started: {startedStr}
                    </span>
                    <span>Completed: {completedStr}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between sm:justify-end gap-4 shrink-0 border-t sm:border-t-0 border-surface-border/60 pt-2 sm:pt-0">
                  <div className="text-right">
                    <span className="text-xs font-mono font-bold text-white block">
                      {exec.completed_steps || 0} / {exec.total_steps || 0} steps
                    </span>
                    <span className="text-2xs text-slate-500">
                      {exec.mode === 'live' ? 'executed' : 'simulated'}
                    </span>
                  </div>

                  <div className="w-8 h-8 rounded-xl bg-surface flex items-center justify-center text-slate-400 group-hover:text-cyan-300 group-hover:bg-cyan-950/40 transition-colors">
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
