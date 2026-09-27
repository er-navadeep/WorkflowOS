import React from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowRight, Clock, Terminal } from 'lucide-react';
import { IntegrationBadge } from '../workflows/WorkflowComponents';
import { EmptyState } from '../common/FeedbackStates';

function formatTimestamp(timestampStr) {
  if (!timestampStr) return '—';
  try {
    const date = new Date(timestampStr);
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHour < 24) return `${diffHour}h ago`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return timestampStr;
  }
}

export function RecentActivitySection({ events = [] }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-200">Recent Activity</h3>
            <p className="text-2xs text-slate-400">Chronological telemetry from desktop activity agent</p>
          </div>
        </div>

        <Link
          to="/activity"
          className="text-xs text-primary-400 hover:text-primary-300 font-medium flex items-center gap-1 group"
        >
          <span>View all activity</span>
          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
        </Link>
      </div>

      {events.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No activity recorded"
          description="Activity logs will appear here as users interact with digital applications."
        />
      ) : (
        <div className="glass-panel rounded-2xl overflow-hidden divide-y divide-surface-border/50">
          {events.map((evt, idx) => (
            <div
              key={evt.event_id || idx}
              className="p-3.5 flex items-start justify-between gap-3 hover:bg-surface-elevated/40 transition-colors"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <IntegrationBadge application={evt.application} />
                  <span className="text-xs font-medium text-slate-200 truncate">
                    {evt.action}
                  </span>
                  {evt.event_type && (
                    <span className="px-1.5 py-0.2 rounded text-2xs font-mono text-slate-500 bg-surface border border-surface-border">
                      {evt.event_type}
                    </span>
                  )}
                </div>

                {evt.target && (
                  <p className="text-2xs text-slate-400 font-mono mt-1 truncate pl-0.5">
                    {evt.target}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-1 text-2xs text-slate-500 font-mono shrink-0 pt-0.5">
                <Clock className="w-3 h-3 text-slate-600" />
                <span>{formatTimestamp(evt.timestamp)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
