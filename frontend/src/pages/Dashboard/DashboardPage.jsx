import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  Activity, 
  Sparkles, 
  GitBranch, 
  CheckSquare, 
  ArrowRight,
  ShieldCheck
} from 'lucide-react';
import { api } from '../../services/api/client';
import { MetricCard } from '../../components/dashboard/MetricCard';
import { WorkflowPipeline } from '../../components/dashboard/WorkflowPipeline';
import { PendingApprovalsSection } from '../../components/dashboard/PendingApprovalsSection';
import { RecentActivitySection } from '../../components/dashboard/RecentActivitySection';
import { DashboardSkeleton } from '../../components/dashboard/DashboardSkeleton';
import { ErrorState } from '../../components/common/FeedbackStates';

function getTimeGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [metrics, setMetrics] = useState({
    eventsCount: null,
    patternsCount: null,
    workflowsCount: null,
    pendingCount: null,
  });

  const [pendingWorkflows, setPendingWorkflows] = useState([]);
  const [recentEvents, setRecentEvents] = useState([]);

  useEffect(() => {
    fetchDashboardMetrics();
  }, []);

  async function fetchDashboardMetrics() {
    setLoading(true);
    setError(null);

    try {
      // Concurrently query the existing backend endpoints
      const [eventsRes, candidatesRes, workflowsRes, pendingRes] = await Promise.allSettled([
        api.getEvents({ limit: 500 }),
        api.getCandidates(),
        api.listWorkflows(),
        api.getPendingWorkflows(),
      ]);

      // 1. Observed events
      let eventsData = [];
      let eventsVal = '—';
      if (eventsRes.status === 'fulfilled' && Array.isArray(eventsRes.value)) {
        eventsData = eventsRes.value;
        eventsVal = eventsData.length >= 500 ? '500+' : eventsData.length;
      }

      // 2. Discovered candidates
      let patternsVal = '—';
      if (candidatesRes.status === 'fulfilled' && Array.isArray(candidatesRes.value)) {
        patternsVal = candidatesRes.value.length;
      }

      // 3. Generated workflows
      let workflowsVal = '—';
      if (workflowsRes.status === 'fulfilled' && Array.isArray(workflowsRes.value)) {
        workflowsVal = workflowsRes.value.length;
      }

      // 4. Pending approvals
      let pendingList = [];
      let pendingVal = '—';
      if (pendingRes.status === 'fulfilled' && Array.isArray(pendingRes.value)) {
        pendingList = pendingRes.value;
        pendingVal = pendingList.length;
      }

      setMetrics({
        eventsCount: eventsVal,
        patternsCount: patternsVal,
        workflowsCount: workflowsVal,
        pendingCount: pendingVal,
      });

      setPendingWorkflows(pendingList);
      setRecentEvents(eventsData.slice(0, 8));
    } catch (err) {
      console.error('Failed to load dashboard metrics:', err);
      setError(new Error("Couldn't load workflow data. Please check connection to the backend server."));
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <div className="max-w-xl mx-auto py-12">
        <ErrorState error={error} onRetry={fetchDashboardMetrics} />
      </div>
    );
  }

  const greeting = getTimeGreeting();

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Welcome / Header Section */}
      <section className="p-6 sm:p-8 rounded-3xl glass-panel relative overflow-hidden flex flex-col sm:flex-row sm:items-center justify-between gap-6 border border-surface-border">
        <div className="space-y-2 max-w-2xl z-10">
          <span className="text-2xs font-mono uppercase tracking-widest text-primary-400 font-semibold flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-primary-400" />
            {greeting}
          </span>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Your workflows, understood.
          </h1>
          <p className="text-sm text-slate-400 leading-relaxed">
            WorkFlowOS observes your work, discovers repetitive patterns, and turns them into workflows you can review and automate.
          </p>
        </div>

        <div className="z-10 shrink-0 flex flex-wrap items-center gap-3">
          <Link
            to="/workflows"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold bg-surface-elevated hover:bg-slate-700 text-slate-300 hover:text-white border border-surface-border transition-all"
          >
            <span>View execution history</span>
          </Link>
          <Link
            to="/approvals"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold bg-primary-600 hover:bg-primary-500 text-white shadow-xl shadow-primary-600/25 transition-all group"
          >
            <span>View pending approvals</span>
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>
      </section>

      {/* Statistics Metric Cards */}
      <section>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <MetricCard
            title="Observed Events"
            value={metrics.eventsCount}
            description="Ingested OS activity telemetry"
            icon={Activity}
            accentColor="indigo"
            to="/activity"
          />
          <MetricCard
            title="Discovered Patterns"
            value={metrics.patternsCount}
            description="Repetitive sequences scored"
            icon={Sparkles}
            accentColor="cyan"
            to="/discovery"
          />
          <MetricCard
            title="Generated Workflows"
            value={metrics.workflowsCount}
            description="Structured definitions"
            icon={GitBranch}
            accentColor="emerald"
            to="/workflows"
          />
          <MetricCard
            title="Pending Approvals"
            value={metrics.pendingCount}
            description="Awaiting reviewer sign-off"
            icon={CheckSquare}
            accentColor="amber"
            to="/approvals"
          />
        </div>
      </section>

      {/* Autonomous Workflow Lifecycle Pipeline */}
      <section>
        <WorkflowPipeline />
      </section>

      {/* Grid: Pending Approvals & Recent Activity */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        <div className="lg:col-span-7">
          <PendingApprovalsSection workflows={pendingWorkflows} />
        </div>
        <div className="lg:col-span-5">
          <RecentActivitySection events={recentEvents} />
        </div>
      </section>
    </div>
  );
}
