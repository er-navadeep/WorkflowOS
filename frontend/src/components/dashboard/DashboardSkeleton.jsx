import React from 'react';

export function DashboardSkeleton() {
  return (
    <div className="space-y-8 max-w-7xl mx-auto animate-pulse">
      {/* Top Banner Skeleton */}
      <div className="p-6 rounded-3xl bg-surface/60 border border-surface-border flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-3 w-28 bg-surface-elevated rounded" />
          <div className="h-7 w-64 bg-surface-elevated rounded" />
          <div className="h-4 w-96 bg-surface-elevated rounded" />
        </div>
        <div className="h-10 w-44 bg-surface-elevated rounded-xl hidden sm:block" />
      </div>

      {/* Metrics Row Skeleton */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="glass-card rounded-2xl p-5 space-y-3 h-36 flex flex-col justify-between">
            <div className="flex justify-between items-center">
              <div className="h-3 w-24 bg-surface-elevated rounded" />
              <div className="w-8 h-8 rounded-xl bg-surface-elevated" />
            </div>
            <div className="space-y-1.5">
              <div className="h-8 w-16 bg-surface-elevated rounded" />
              <div className="h-3 w-32 bg-surface-elevated rounded" />
            </div>
          </div>
        ))}
      </div>

      {/* Pipeline Skeleton */}
      <div className="glass-panel rounded-2xl p-6 space-y-4">
        <div className="h-4 w-48 bg-surface-elevated rounded" />
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-28 rounded-xl bg-surface-elevated/40 border border-surface-border p-3 space-y-2" />
          ))}
        </div>
      </div>

      {/* Two Columns Grid Skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-7 space-y-4">
          <div className="h-5 w-36 bg-surface-elevated rounded" />
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <div key={i} className="h-32 rounded-2xl bg-surface-elevated/30 border border-surface-border" />
            ))}
          </div>
        </div>
        <div className="lg:col-span-5 space-y-4">
          <div className="h-5 w-36 bg-surface-elevated rounded" />
          <div className="h-64 rounded-2xl bg-surface-elevated/30 border border-surface-border" />
        </div>
      </div>
    </div>
  );
}
