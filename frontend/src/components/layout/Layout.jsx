import React, { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { api } from '../../services/api/client';

const PAGE_TITLES = {
  '/dashboard': { title: 'Operational Dashboard', subtitle: 'Overview of activity, discoveries, and workflow lifecycle' },
  '/discovery': { title: 'Workflow Discovery', subtitle: 'WorkFlowOS found these repetitive patterns in your activity.' },
  '/workflows': { title: 'Workflows', subtitle: 'AI-generated workflow definitions created from discovered patterns.' },
  '/approvals': { title: 'Approval Queue', subtitle: 'Review AI-generated workflows before they become eligible for automation.' },
  '/activity': { title: 'Activity', subtitle: 'Review the digital activity WorkFlowOS has observed.' },
};

export function Layout() {
  const location = useLocation();
  const [health, setHealth] = useState('connected');
  const [pendingCount, setPendingCount] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);

  const getPageMeta = (pathname) => {
    if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
    if (pathname.startsWith('/workflows/')) {
      return {
        title: 'Workflow Detail',
        subtitle: 'AI-generated workflow definition and execution pipeline.',
      };
    }
    return {
      title: 'WorkFlowOS',
      subtitle: 'AI-Powered OS-Level Workflow Automation',
    };
  };

  const currentMeta = getPageMeta(location.pathname);

  useEffect(() => {
    // Initial health check
    api.getHealth()
      .then(res => setHealth(res.status))
      .catch(() => setHealth('unreachable'));

    // Fetch pending count for sidebar badge
    api.getPendingWorkflows()
      .then(res => setPendingCount(Array.isArray(res) ? res.length : 0))
      .catch(() => setPendingCount(0));
  }, [location.pathname]);

  return (
    <div className="flex h-screen bg-background text-slate-100 overflow-hidden font-sans">
      <Sidebar 
        pendingCount={pendingCount} 
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar 
          title={currentMeta.title} 
          subtitle={currentMeta.subtitle} 
          healthStatus={health} 
          onOpenMobile={() => setMobileOpen(true)}
        />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <Outlet context={{ setPendingCount }} />
        </main>
      </div>
    </div>
  );
}
