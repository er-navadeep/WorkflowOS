import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Sparkles, 
  GitBranch, 
  CheckSquare, 
  Activity, 
  Cpu, 
  ShieldCheck,
  X
} from 'lucide-react';

const NAV_ITEMS = [
  { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard },
  { label: 'Discovery', to: '/discovery', icon: Sparkles },
  { label: 'Workflows', to: '/workflows', icon: GitBranch },
  { label: 'Approvals', to: '/approvals', icon: CheckSquare },
  { label: 'Activity', to: '/activity', icon: Activity },
];

export function Sidebar({ pendingCount = 0, mobileOpen = false, onCloseMobile }) {
  return (
    <>
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div 
          onClick={onCloseMobile}
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
        />
      )}

      {/* Sidebar Panel */}
      <aside
        className={`fixed lg:static top-0 bottom-0 left-0 z-50 w-64 bg-surface border-r border-surface-border flex flex-col shrink-0 select-none transition-transform duration-300 ease-in-out ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Branding */}
        <div className="p-6 border-b border-surface-border/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-primary-600 to-accent-cyan p-0.5 shadow-lg shadow-primary-600/25">
              <div className="w-full h-full bg-surface rounded-[10px] flex items-center justify-center">
                <Cpu className="w-5 h-5 text-accent-cyan" />
              </div>
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-1.5">
                WorkFlow<span className="text-accent-cyan">OS</span>
              </h1>
              <span className="text-2xs font-mono uppercase tracking-widest text-slate-500">Autonomous Ops</span>
            </div>
          </div>

          {/* Close button on mobile */}
          <button
            onClick={onCloseMobile}
            className="p-1 text-slate-400 hover:text-white rounded-lg lg:hidden"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 p-4 space-y-1.5 overflow-y-auto">
          <div className="px-3 pb-2 text-2xs font-semibold uppercase tracking-wider text-slate-500">
            Navigation
          </div>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onCloseMobile}
                className={({ isActive }) =>
                  `flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-primary-600/15 text-primary-400 border border-primary-500/30 shadow-inner font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-surface-elevated/60'
                  }`
                }
              >
                <div className="flex items-center gap-3">
                  <Icon className="w-4 h-4 shrink-0" />
                  <span>{item.label}</span>
                </div>
                {item.to === '/approvals' && pendingCount > 0 && (
                  <span className="px-2 py-0.5 rounded-full text-xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    {pendingCount}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Lifecycle Status Box */}
        <div className="p-4 border-t border-surface-border/80">
          <div className="p-3 rounded-xl bg-surface-elevated/50 border border-surface-border text-xs">
            <div className="flex items-center gap-1.5 text-slate-300 font-medium mb-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>Phase 7 Verified</span>
            </div>
            <p className="text-slate-500 text-2xs leading-relaxed">
              Human approval gate is enforced. AI proposals require explicit reviewer signoff.
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
