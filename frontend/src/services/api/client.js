/**
 * WorkFlowOS API Client
 * Centralized communication layer connecting the frontend to the FastAPI backend.
 */

const API_BASE = '/api/v1';

async function request(endpoint, options = {}) {
  const url = endpoint.startsWith('http') || endpoint.startsWith('/health')
    ? endpoint
    : `${API_BASE}${endpoint}`;

  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  try {
    const response = await fetch(url, config);
    if (!response.ok) {
      let errorDetail = 'API request failed';
      try {
        const errJson = await response.json();
        errorDetail = errJson.detail?.message || errJson.message || JSON.stringify(errJson.detail) || response.statusText;
      } catch {
        errorDetail = await response.text() || response.statusText;
      }
      const err = new Error(errorDetail);
      err.status = response.status;
      throw err;
    }
    return await response.json();
  } catch (error) {
    console.error(`[API Error] ${options.method || 'GET'} ${url}:`, error.message);
    throw error;
  }
}

export const api = {
  // --- System ---
  getHealth: () => request('/health'),

  // --- Activity Events ---
  getEvents: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/events${query ? `?${query}` : ''}`);
  },
  ingestEvent: (eventData) => request('/events', {
    method: 'POST',
    body: JSON.stringify(eventData),
  }),
  ingestBatch: (events) => request('/events/batch', {
    method: 'POST',
    body: JSON.stringify({ events }),
  }),

  // --- Discovery ---
  runDiscovery: (params = {}) => request('/discovery/run', {
    method: 'POST',
    body: JSON.stringify(params),
  }),
  getCandidates: () => request('/discovery/candidates'),
  getCandidateById: (id) => request(`/discovery/candidates/${id}`),

  // --- Understanding ---
  generateUnderstanding: (candidateId) => request(`/understanding/${candidateId}`, {
    method: 'POST',
  }),
  getUnderstanding: (candidateId) => request(`/understanding/${candidateId}`),
  listUnderstandings: () => request('/understanding'),

  // --- Workflows ---
  generateWorkflow: (understandingId) => request(`/workflows/generate/${understandingId}`, {
    method: 'POST',
  }),
  listWorkflows: () => request('/workflows'),
  getWorkflow: (workflowId) => request(`/workflows/${workflowId}`),
  getWorkflowByUnderstanding: (understandingId) => request(`/workflows/by-understanding/${understandingId}`),

  // --- Approval (Phase 7) ---
  getPendingWorkflows: () => request('/workflows/pending'),
  approveWorkflow: (workflowId, payload) => request(`/workflows/${workflowId}/approve`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  rejectWorkflow: (workflowId, payload) => request(`/workflows/${workflowId}/reject`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),

  // --- Executions (Phase 8) ---
  startDryRun: (workflowId, payload = {}) => request(`/executions/dry-run/${workflowId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  startLiveExecution: (workflowId, payload = {}) => request(`/executions/live/${workflowId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  getExecution: (executionId) => request(`/executions/${executionId}`),
  listWorkflowExecutions: (workflowId, limit = 50) => {
    const query = workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}&limit=${limit}` : `?limit=${limit}`;
    return request(`/executions${query}`);
  },

  // --- Automatic Triggers & Automation (Phase 8.11) ---
  listTriggers: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/triggers${query ? `?${query}` : ''}`);
  },
  getTrigger: (workflowId) => request(`/triggers/${encodeURIComponent(workflowId)}`),
  enableTrigger: (workflowId) => request(`/triggers/${encodeURIComponent(workflowId)}/enable`, {
    method: 'POST',
  }),
  disableTrigger: (workflowId) => request(`/triggers/${encodeURIComponent(workflowId)}/disable`, {
    method: 'POST',
  }),
  pollTrigger: (workflowId, dryRun = false) => request(`/triggers/${encodeURIComponent(workflowId)}/poll?dry_run=${dryRun}`, {
    method: 'POST',
  }),
  getWorkflowFeedback: (workflowId) => request(`/triggers/${encodeURIComponent(workflowId)}/feedback`),
};

