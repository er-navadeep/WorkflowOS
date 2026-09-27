import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { DashboardPage } from './pages/Dashboard/DashboardPage';
import { DiscoveryPage } from './pages/DiscoveredWorkflows/DiscoveryPage';
import { WorkflowsPage } from './pages/WorkflowDetails/WorkflowsPage';
import { WorkflowDetailPage } from './pages/WorkflowDetails/WorkflowDetailPage';
import { ApprovalsPage } from './pages/Approvals/ApprovalsPage';
import { ActivityPage } from './pages/Activity/ActivityPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="discovery" element={<DiscoveryPage />} />
          <Route path="workflows" element={<WorkflowsPage />} />
          <Route path="workflows/:workflowId" element={<WorkflowDetailPage />} />
          <Route path="approvals" element={<ApprovalsPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
