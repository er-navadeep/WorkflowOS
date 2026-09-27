import React, { useEffect, useState, useMemo } from 'react';
import { 
  Activity, 
  Search, 
  Filter, 
  RefreshCw, 
  Layers, 
  Database, 
  Hash, 
  Clock, 
  ShieldCheck, 
  AlertTriangle,
  X
} from 'lucide-react';
import { api } from '../../services/api/client';
import { ActivityTimeline } from '../../components/activity/ActivityTimeline';
import { EventDetailModal } from '../../components/activity/EventDetailModal';
import { IntegrationBadge } from '../../components/workflows/WorkflowComponents';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/FeedbackStates';

export function ActivityPage() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [limit, setLimit] = useState(100);

  // Filters state
  const [search, setSearch] = useState('');
  const [appFilter, setAppFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sessionFilter, setSessionFilter] = useState('all');

  // Selected event for modal
  const [selectedEvent, setSelectedEvent] = useState(null);

  useEffect(() => {
    loadEvents();
  }, [limit]);

  async function loadEvents() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getEvents({ limit });
      setEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load events:', err);
      setError(new Error("Unable to load activity."));
    } finally {
      setLoading(false);
    }
  }

  // Extract dynamic filter options from loaded data
  const uniqueApps = useMemo(() => {
    return Array.from(new Set(events.map((e) => e.application).filter(Boolean))).sort();
  }, [events]);

  const uniqueTypes = useMemo(() => {
    return Array.from(new Set(events.map((e) => e.event_type).filter(Boolean))).sort();
  }, [events]);

  const uniqueSessions = useMemo(() => {
    return Array.from(new Set(events.map((e) => e.session_id).filter(Boolean))).sort();
  }, [events]);

  // Calculate summary metrics strictly from loaded data
  const totalEventsLoaded = events.length;
  const applicationsObservedCount = uniqueApps.length;
  const eventTypesCount = uniqueTypes.length;
  const sessionsCount = uniqueSessions.length;

  // Filter events client-side
  const filteredEvents = useMemo(() => {
    return events.filter((evt) => {
      // Application filter
      if (appFilter !== 'all' && (evt.application || '').toLowerCase() !== appFilter.toLowerCase()) {
        return false;
      }
      // Event Type filter
      if (typeFilter !== 'all' && (evt.event_type || '').toLowerCase() !== typeFilter.toLowerCase()) {
        return false;
      }
      // Session filter
      if (sessionFilter !== 'all' && evt.session_id !== sessionFilter) {
        return false;
      }
      // Search filter
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesApp = (evt.application || '').toLowerCase().includes(q);
        const matchesAction = (evt.action || '').toLowerCase().includes(q);
        const matchesType = (evt.event_type || '').toLowerCase().includes(q);
        const matchesTarget = (evt.target || '').toLowerCase().includes(q);
        const matchesSession = (evt.session_id || '').toLowerCase().includes(q);
        if (!matchesApp && !matchesAction && !matchesType && !matchesTarget && !matchesSession) {
          return false;
        }
      }
      return true;
    });
  }, [events, appFilter, typeFilter, sessionFilter, search]);

  const hasActiveFilters = appFilter !== 'all' || typeFilter !== 'all' || sessionFilter !== 'all' || search.trim() !== '';

  const clearFilters = () => {
    setSearch('');
    setAppFilter('all');
    setTypeFilter('all');
    setSessionFilter('all');
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* 1. Page Header & Explanatory Section */}
      <section className="space-y-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Activity
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Review the digital activity WorkFlowOS has observed.
          </p>
        </div>

        {/* Informational Callout & Warning Banner */}
        <div className="p-4 rounded-2xl glass-panel border border-surface-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-cyan-950/60 border border-cyan-800/50 text-cyan-400 shrink-0 mt-0.5 sm:mt-0">
              <Activity className="w-4 h-4" />
            </div>
            <div className="text-xs text-slate-300 leading-relaxed">
              <span className="font-semibold text-white block">Digital Telemetry Stream (OBSERVE)</span>
              WorkFlowOS converts activity across applications into structured events that can be analyzed for repetitive workflow patterns.
              <p className="text-cyan-300 mt-1 font-mono text-2xs">
                Observed activity is telemetry used for workflow discovery. It is not an executable workflow.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
            {/* Limit Selector */}
            <div className="flex items-center gap-1 text-2xs font-mono text-slate-400 bg-surface px-2.5 py-1 rounded-xl border border-surface-border">
              <span>Limit:</span>
              {[50, 100, 200].map((lim) => (
                <button
                  key={lim}
                  onClick={() => setLimit(lim)}
                  className={`px-1.5 py-0.5 rounded ${
                    limit === lim ? 'bg-cyan-500/20 text-cyan-300 font-bold' : 'hover:text-white'
                  }`}
                >
                  {lim}
                </button>
              ))}
            </div>

            <button
              onClick={loadEvents}
              disabled={loading}
              className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-xl bg-surface-elevated hover:bg-slate-700 text-slate-300 border border-surface-border transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </section>

      {/* 2. Activity Summary Section */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Events Loaded */}
        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Total Events Loaded</span>
            <div className="p-2 rounded-xl bg-cyan-950/40 border border-cyan-800/50 text-cyan-400">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-white font-mono">
              {loading ? '—' : totalEventsLoaded}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Telemetry records in memory</p>
          </div>
        </div>

        {/* Applications Observed */}
        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Applications Observed</span>
            <div className="p-2 rounded-xl bg-primary-950/40 border border-primary-800/50 text-primary-400">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-primary-300 font-mono">
              {loading ? '—' : applicationsObservedCount}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Unique source environments</p>
          </div>
        </div>

        {/* Event Types */}
        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Event Types</span>
            <div className="p-2 rounded-xl bg-indigo-950/40 border border-indigo-800/50 text-indigo-400">
              <Database className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-indigo-300 font-mono">
              {loading ? '—' : eventTypesCount}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Classification categories</p>
          </div>
        </div>

        {/* Sessions */}
        <div className="glass-card rounded-2xl p-5 border border-surface-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Sessions</span>
            <div className="p-2 rounded-xl bg-emerald-950/40 border border-emerald-800/50 text-emerald-400">
              <Hash className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold tracking-tight text-emerald-300 font-mono">
              {loading ? '—' : sessionsCount}
            </span>
            <p className="text-2xs text-slate-400 mt-1">Execution session clusters</p>
          </div>
        </div>
      </section>

      {/* 3. Filter Bar & Search */}
      <section className="space-y-4">
        <div className="p-4 rounded-2xl glass-panel border border-surface-border flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          {/* Search Box */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search action, target, session, or application..."
              className="w-full pl-9 pr-3 py-2 rounded-xl bg-surface border border-surface-border text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Dropdown Filters */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Application Filter */}
            <select
              value={appFilter}
              onChange={(e) => setAppFilter(e.target.value)}
              className="px-3 py-2 rounded-xl bg-surface border border-surface-border text-xs text-slate-200 focus:outline-none focus:border-cyan-500 transition-colors"
            >
              <option value="all">All Applications ({uniqueApps.length})</option>
              {uniqueApps.map((app) => (
                <option key={app} value={app}>
                  {app}
                </option>
              ))}
            </select>

            {/* Event Type Filter */}
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="px-3 py-2 rounded-xl bg-surface border border-surface-border text-xs text-slate-200 focus:outline-none focus:border-cyan-500 transition-colors"
            >
              <option value="all">All Event Types ({uniqueTypes.length})</option>
              {uniqueTypes.map((typ) => (
                <option key={typ} value={typ}>
                  {typ}
                </option>
              ))}
            </select>

            {/* Session Filter */}
            <select
              value={sessionFilter}
              onChange={(e) => setSessionFilter(e.target.value)}
              className="px-3 py-2 rounded-xl bg-surface border border-surface-border text-xs text-slate-200 focus:outline-none focus:border-cyan-500 transition-colors max-w-[180px] truncate"
            >
              <option value="all">All Sessions ({uniqueSessions.length})</option>
              {uniqueSessions.map((sess) => (
                <option key={sess} value={sess}>
                  {sess}
                </option>
              ))}
            </select>

            {/* Clear Filters Button */}
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="px-3 py-2 text-xs font-semibold rounded-xl bg-surface-elevated hover:bg-slate-700 text-rose-300 border border-rose-900/40 transition-colors flex items-center gap-1.5"
              >
                <X className="w-3.5 h-3.5" />
                <span>Clear</span>
              </button>
            )}
          </div>
        </div>

        {/* Filter Count Bar */}
        <div className="flex items-center justify-between text-2xs font-mono text-slate-400 px-1">
          <span>
            Showing {filteredEvents.length} of {events.length} loaded events
          </span>
          <span>
            Telemetry source: MongoDB (Reverse-Chronological)
          </span>
        </div>

        {/* Loading State with Timeline Skeleton */}
        {loading && (
          <div className="space-y-4 animate-pulse pl-6 sm:pl-8 before:absolute before:left-3 before:top-0 before:bottom-0 before:w-0.5 before:bg-surface-border">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="glass-card rounded-2xl p-5 h-24 flex items-center justify-between">
                <div className="space-y-2 w-3/4">
                  <div className="h-3 w-32 bg-surface-elevated rounded" />
                  <div className="h-4 w-48 bg-surface-elevated rounded" />
                  <div className="h-2.5 w-64 bg-surface-elevated rounded" />
                </div>
                <div className="h-8 w-16 bg-surface-elevated rounded-xl" />
              </div>
            ))}
          </div>
        )}

        {/* Error State */}
        {!loading && error && (
          <div className="max-w-xl mx-auto py-8">
            <ErrorState error={error} onRetry={loadEvents} />
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && filteredEvents.length === 0 && (
          <EmptyState
            icon={Activity}
            title={events.length === 0 ? "No activity observed yet" : "No events match filters"}
            description={
              events.length === 0
                ? "WorkFlowOS will display observed application activity here as events are captured."
                : "No activity events match your current search and filter criteria."
            }
            actionText={hasActiveFilters ? "Clear Filters" : undefined}
            onAction={hasActiveFilters ? clearFilters : undefined}
          />
        )}

        {/* Timeline View */}
        {!loading && !error && filteredEvents.length > 0 && (
          <ActivityTimeline
            events={filteredEvents}
            onSelectEvent={(evt) => setSelectedEvent(evt)}
          />
        )}
      </section>

      {/* 4. Event Detail Modal */}
      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  );
}
