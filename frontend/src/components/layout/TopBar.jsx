import React from 'react';
import { Menu, Shield, Activity, User, Bell } from 'lucide-react';

export function TopBar({ title, subtitle, healthStatus = 'connected', onOpenMobile }) {
  const isHealthy = healthStatus === 'connected' || healthStatus === 'ok';

  return (
    <header className="h-16 px-4 sm:px-8 bg-surface/80 backdrop-blur-md border-b border-surface-border flex items-center justify-between shrink-0 sticky top-0 z-20">
      {/* Left: Mobile hamburger + Title & Context */}
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenMobile}
          className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-surface-elevated lg:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div>
          <h2 className="text-sm sm:text-base font-semibold text-white tracking-tight">{title}</h2>
          {subtitle && (
            <p className="text-2xs text-slate-400 font-normal hidden sm:block">{subtitle}</p>
          )}
        </div>
      </div>

      {/* Right controls: Health Pill + User Placeholder */}
      <div className="flex items-center gap-3 sm:gap-4">
        {/* Backend System Health Pill */}
        <div className="flex items-center gap-2 px-2.5 sm:px-3 py-1 rounded-full bg-surface-elevated/70 border border-surface-border text-xs">
          <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`} />
          <span className="font-mono text-slate-300 text-2xs">
            Backend: {isHealthy ? 'Online' : 'Offline'}
          </span>
        </div>

        {/* User profile avatar placeholder */}
        <div className="flex items-center gap-2.5 pl-2 border-l border-surface-border">
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-primary-600 to-indigo-800 flex items-center justify-center text-white font-medium text-xs shadow-md">
            AD
          </div>
          <div className="hidden md:block text-left">
            <span className="text-xs font-medium text-slate-200 block leading-tight">Admin Reviewer</span>
            <span className="text-2xs font-mono text-slate-500 block">Phase 7 Reviewer</span>
          </div>
        </div>
      </div>
    </header>
  );
}
