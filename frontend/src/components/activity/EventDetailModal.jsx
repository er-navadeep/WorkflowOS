import React from 'react';
import { 
  X, 
  Activity, 
  Clock, 
  Terminal, 
  Layers, 
  ShieldCheck, 
  Calendar, 
  Database,
  Hash,
  Eye
} from 'lucide-react';
import { IntegrationBadge } from '../workflows/WorkflowComponents';

export function EventDetailModal({ event, onClose }) {
  if (!event) return null;

  const formattedTime = event.timestamp
    ? new Date(event.timestamp).toLocaleString('en-US', {
        dateStyle: 'medium',
        timeStyle: 'medium',
      })
    : '—';

  // Sanitize metadata to never display secrets or credentials
  const sanitizedMetadata = {};
  if (event.metadata && typeof event.metadata === 'object') {
    Object.entries(event.metadata).forEach(([key, value]) => {
      const lowerKey = key.toLowerCase();
      if (
        lowerKey.includes('token') ||
        lowerKey.includes('secret') ||
        lowerKey.includes('password') ||
        lowerKey.includes('api_key') ||
        lowerKey.includes('apikey') ||
        lowerKey.includes('credential')
      ) {
        return; // skip sensitive keys
      }
      sanitizedMetadata[key] = value;
    });
  }

  const hasMetadata = Object.keys(sanitizedMetadata).length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/75 backdrop-blur-md animate-fadeIn">
      <div className="glass-panel w-full max-w-lg rounded-3xl border border-surface-border shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="p-6 border-b border-surface-border/80 flex items-start justify-between gap-4 bg-surface/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-cyan-950/60 border border-cyan-800/50 flex items-center justify-center text-cyan-400 shrink-0">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-2xs font-mono uppercase tracking-widest text-cyan-400 font-bold">
                  Observed Event Detail
                </span>
                <IntegrationBadge application={event.application} />
              </div>
              <h3 className="text-base font-bold text-white tracking-tight mt-0.5 font-mono">
                {event.action}
              </h3>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-surface-elevated transition-colors shrink-0"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Informational Notice */}
          <div className="p-3.5 rounded-xl bg-cyan-950/30 border border-cyan-800/40 text-xs text-slate-300 flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
            <div className="leading-relaxed">
              <span className="font-semibold text-cyan-300 block">Observed Activity Telemetry</span>
              Captured activity from your desktop/apps used as raw empirical evidence for workflow pattern discovery. Not an automation script.
            </div>
          </div>

          {/* Core Properties Grid */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Application</span>
              <div className="mt-1">
                <IntegrationBadge application={event.application} />
              </div>
            </div>

            <div className="p-3 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Event Type</span>
              <span className="text-xs font-mono font-bold text-slate-200 mt-1 block">
                {event.event_type}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Action</span>
              <span className="text-xs font-mono font-bold text-cyan-300 mt-1 block">
                {event.action}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-surface/70 border border-surface-border">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">Target Entity</span>
              <span className="text-xs font-mono text-slate-200 mt-1 block truncate" title={event.target}>
                {event.target || '—'}
              </span>
            </div>
          </div>

          {/* Session & Timestamp */}
          <div className="space-y-2 text-xs font-mono">
            <div className="p-3 rounded-xl bg-surface/70 border border-surface-border space-y-1">
              <span className="text-2xs text-slate-500 uppercase tracking-wider block">Session Identifier</span>
              <span className="text-xs text-indigo-300 block select-all break-all">
                {event.session_id || '—'}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-surface/70 border border-surface-border space-y-1">
              <span className="text-2xs text-slate-500 uppercase tracking-wider block">Timestamp</span>
              <span className="text-xs text-slate-300 block">
                {formattedTime}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-surface/70 border border-surface-border space-y-1">
              <span className="text-2xs text-slate-500 uppercase tracking-wider block">Event UUID</span>
              <span className="text-2xs text-slate-400 block select-all break-all">
                {event.event_id}
              </span>
            </div>
          </div>

          {/* Metadata */}
          {hasMetadata && (
            <div className="space-y-2">
              <span className="text-2xs font-mono text-slate-500 uppercase tracking-wider block">
                Event Payload Context
              </span>
              <div className="p-3 rounded-xl bg-surface/90 border border-surface-border">
                <pre className="text-2xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(sanitizedMetadata, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-surface-border bg-surface/80 flex items-center justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold rounded-xl bg-surface-elevated hover:bg-slate-700 text-slate-200 transition-colors"
          >
            Close Details
          </button>
        </div>
      </div>
    </div>
  );
}
