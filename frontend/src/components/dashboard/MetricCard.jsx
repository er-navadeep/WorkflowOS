import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export function MetricCard({ title, value, description, icon: Icon, to, accentColor = 'indigo' }) {
  const colorStyles = {
    indigo: 'text-indigo-400 bg-indigo-950/40 border-indigo-800/50',
    cyan: 'text-cyan-400 bg-cyan-950/40 border-cyan-800/50',
    emerald: 'text-emerald-400 bg-emerald-950/40 border-emerald-800/50',
    amber: 'text-amber-400 bg-amber-950/40 border-amber-800/50',
  };

  const badgeClass = colorStyles[accentColor] || colorStyles.indigo;
  const isAvailable = value !== undefined && value !== null && value !== '—';

  const CardContent = (
    <div className="glass-card rounded-2xl p-5 flex flex-col justify-between h-full group hover:border-slate-600 transition-all">
      <div>
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-slate-400">{title}</span>
          <div className={`p-2 rounded-xl border ${badgeClass}`}>
            <Icon className="w-4 h-4" />
          </div>
        </div>

        <div className="mt-4">
          <span className="text-3xl font-bold tracking-tight text-white font-mono">
            {isAvailable ? value : '—'}
          </span>
          <p className="text-2xs text-slate-400 mt-1">
            {isAvailable ? description : 'Data unavailable'}
          </p>
        </div>
      </div>

      {to && (
        <div className="pt-3 mt-3 border-t border-surface-border/50 flex items-center justify-between text-2xs text-slate-400 group-hover:text-primary-400 transition-colors">
          <span>View details</span>
          <ArrowUpRight className="w-3.5 h-3.5 opacity-60 group-hover:opacity-100 transition-opacity" />
        </div>
      )}
    </div>
  );

  if (to) {
    return (
      <Link to={to} className="block h-full">
        {CardContent}
      </Link>
    );
  }

  return CardContent;
}
