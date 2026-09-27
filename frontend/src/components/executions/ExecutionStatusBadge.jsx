import React from 'react';
import { 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Loader2, 
  AlertTriangle, 
  Ban, 
  AlertCircle,
  ShieldCheck,
  Cpu
} from 'lucide-react';

export function ExecutionStatusBadge({ status, size = 'default' }) {
  const configs = {
    pending: {
      label: 'Pending',
      classes: 'bg-amber-950/40 text-amber-300 border-amber-800/50 shadow-amber-900/10',
      icon: Clock,
      animate: false,
    },
    running: {
      label: 'Running',
      classes: 'bg-blue-950/40 text-blue-300 border-blue-800/50 shadow-blue-900/10',
      icon: Loader2,
      animate: true,
    },
    completed: {
      label: 'Completed',
      classes: 'bg-emerald-950/40 text-emerald-300 border-emerald-800/50 shadow-emerald-900/10',
      icon: CheckCircle2,
      animate: false,
    },
    failed: {
      label: 'Failed',
      classes: 'bg-rose-950/40 text-rose-300 border-rose-800/50 shadow-rose-900/10',
      icon: XCircle,
      animate: false,
    },
    cancelled: {
      label: 'Cancelled',
      classes: 'bg-slate-800 text-slate-300 border-slate-700',
      icon: Ban,
      animate: false,
    },
    needs_intervention: {
      label: 'Needs Intervention',
      classes: 'bg-purple-950/40 text-purple-300 border-purple-800/50 shadow-purple-900/10',
      icon: AlertCircle,
      animate: false,
    },
    dry_run: {
      label: 'Simulated (Dry Run)',
      classes: 'bg-cyan-950/40 text-cyan-300 border-cyan-800/50 shadow-cyan-900/10',
      icon: CheckCircle2,
      animate: false,
    },
  };

  const config = configs[status] || {
    label: status || 'Unknown',
    classes: 'bg-slate-800 text-slate-400 border-slate-700',
    icon: Clock,
    animate: false,
  };

  const Icon = config.icon;
  const sizeClasses = size === 'sm' 
    ? 'px-2 py-0.5 text-2xs gap-1' 
    : 'px-2.5 py-1 text-xs gap-1.5';
  const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5';

  return (
    <span 
      className={`inline-flex items-center font-medium font-mono rounded-full border shadow-sm ${sizeClasses} ${config.classes}`}
    >
      <Icon className={`${iconSize} ${config.animate ? 'animate-spin' : ''}`} />
      <span>{config.label}</span>
    </span>
  );
}

export function ExecutionModeBadge({ mode = 'dry_run', size = 'default' }) {
  const isDryRun = mode === 'dry_run';
  const sizeClasses = size === 'sm' 
    ? 'px-2 py-0.5 text-2xs gap-1' 
    : 'px-2.5 py-1 text-xs gap-1.5';
  const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5';

  if (isDryRun) {
    return (
      <span 
        className={`inline-flex items-center font-bold font-mono tracking-wider uppercase rounded-full bg-cyan-950/60 text-cyan-300 border border-cyan-700/60 shadow-sm ${sizeClasses}`}
        title="Simulation only — no external actions are performed"
      >
        <ShieldCheck className={`${iconSize} text-cyan-400`} />
        <span>DRY RUN</span>
      </span>
    );
  }

  return (
    <span 
      className={`inline-flex items-center font-bold font-mono tracking-wider uppercase rounded-full bg-slate-800 text-slate-300 border border-slate-700 shadow-sm ${sizeClasses}`}
    >
      <Cpu className={`${iconSize}`} />
      <span>LIVE</span>
    </span>
  );
}
