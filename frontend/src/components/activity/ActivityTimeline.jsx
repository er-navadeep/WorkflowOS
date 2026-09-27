import React from 'react';
import { Clock, Layers, ArrowRight, Eye, Hash, Activity } from 'lucide-react';
import { IntegrationBadge } from '../workflows/WorkflowComponents';

export function ActivityTimeline({ events = [], onSelectEvent }) {
  if (!events.length) return null;

  return (
    <div className="relative pl-6 sm:pl-8 space-y-4 before:absolute before:left-3 sm:before:left-4 before:top-3 before:bottom-3 before:w-0.5 before:bg-surface-border">
      {events.map((evt, idx) => {
        const dateObj = evt.timestamp ? new Date(evt.timestamp) : null;
        const timeStr = dateObj
          ? dateObj.toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })
          : '—';
        const dateStr = dateObj ? dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';

        return (
          <div key={evt.event_id || idx} className="relative group">
            {/* Timeline Node Circle */}
            <div className="absolute -left-6 sm:-left-8 top-4 w-3 sm:w-3.5 h-3 sm:h-3.5 rounded-full bg-surface border-2 border-slate-600 group-hover:border-cyan-400 group-hover:scale-110 transition-all z-10" />

            {/* Event Card */}
            <div 
              onClick={() => onSelectEvent(evt)}
              className="glass-card rounded-2xl p-4 sm:p-5 border border-surface-border hover:border-slate-600 transition-all cursor-pointer flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
            >
              <div className="space-y-2 flex-1 min-w-0">
                {/* Meta Header */}
                <div className="flex items-center gap-2 flex-wrap text-2xs font-mono">
                  <span className="text-slate-400 font-semibold flex items-center gap-1">
                    <Clock className="w-3 h-3 text-cyan-400" />
                    {timeStr}
                    {dateStr && <span className="text-slate-500 font-normal">({dateStr})</span>}
                  </span>

                  <span className="text-slate-600">•</span>
                  <IntegrationBadge application={evt.application} />

                  <span className="text-slate-600">•</span>
                  <span className="px-2 py-0.5 rounded bg-surface border border-surface-border text-slate-400 uppercase font-medium">
                    {evt.event_type}
                  </span>
                </div>

                {/* Action & Target Description */}
                <div>
                  <h4 className="text-sm font-bold text-white font-mono group-hover:text-cyan-300 transition-colors">
                    {evt.action}
                  </h4>
                  {evt.target && (
                    <p className="text-xs text-slate-300 mt-0.5 truncate">
                      Target: <span className="text-slate-200 font-medium font-mono">{evt.target}</span>
                    </p>
                  )}
                </div>

                {/* Session Identifier */}
                {evt.session_id && (
                  <div className="flex items-center gap-1.5 text-2xs font-mono text-slate-500">
                    <Hash className="w-3 h-3 text-indigo-400" />
                    <span>Session:</span>
                    <span className="text-indigo-300 truncate max-w-[200px] sm:max-w-xs">{evt.session_id}</span>
                  </div>
                )}
              </div>

              {/* View Action Trigger */}
              <div className="flex items-center gap-1.5 text-xs font-semibold text-cyan-400 group-hover:text-cyan-300 shrink-0 self-end sm:self-center">
                <span>Inspect</span>
                <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
