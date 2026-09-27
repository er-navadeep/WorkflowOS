import React from 'react';
import { Loader2 } from 'lucide-react';

export function LoadingState({ message = 'Loading WorkFlowOS data...', height = 'h-64' }) {
  return (
    <div className={`flex flex-col items-center justify-center ${height} text-slate-400`}>
      <Loader2 className="w-8 h-8 text-primary-500 animate-spin mb-3" />
      <p className="text-sm font-medium tracking-wide">{message}</p>
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="p-6 rounded-xl bg-red-950/30 border border-red-800/50 text-red-200">
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-semibold text-red-400">Failed to load content</h4>
          <p className="text-sm mt-1 text-red-300/80">{error?.message || String(error)}</p>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="px-3 py-1.5 text-xs font-medium bg-red-900/60 hover:bg-red-800 text-red-100 rounded-lg transition-colors border border-red-700/50"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, description, actionText, onAction }) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl glass-panel border border-dashed border-surface-border">
      {Icon && (
        <div className="w-12 h-12 rounded-xl bg-surface-elevated/80 flex items-center justify-center text-slate-400 mb-4 border border-surface-border">
          <Icon className="w-6 h-6" />
        </div>
      )}
      <h3 className="text-base font-semibold text-slate-200">{title}</h3>
      <p className="text-sm text-slate-400 mt-1 max-w-sm">{description}</p>
      {actionText && onAction && (
        <button
          onClick={onAction}
          className="mt-5 px-4 py-2 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-500 text-white shadow-lg shadow-primary-500/20 transition-all"
        >
          {actionText}
        </button>
      )}
    </div>
  );
}
