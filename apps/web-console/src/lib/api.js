import axios from 'axios';

const trimTrailingSlash = (value) => value.replace(/\/+$/, '');
const compactParams = (params = {}) =>
    Object.fromEntries(
        Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ''),
    );

export const API_BASE = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL || '/api');

export const api = axios.create({
    baseURL: API_BASE,
    withCredentials: true,
});

export const apiUrl = (path = '') => {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${API_BASE}${normalizedPath}`;
};

export const agentApi = {
    overview: async (params = {}) => (await api.get('/agent/overview', { params: compactParams(params) })).data,
    runtimeStatus: async () => (await api.get('/agent/runtime-status')).data,
    listAlerts: async (params = {}) => (await api.get('/agent/alerts', { params: compactParams(params) })).data,
    listSubscriptions: async (params = {}) => (await api.get('/agent/subscriptions', { params: compactParams(params) })).data,
    createSubscription: async (payload) => (await api.post('/agent/subscriptions', payload)).data,
    updateSubscription: async (subscriptionId, payload) =>
        (await api.put(`/agent/subscriptions/${subscriptionId}`, payload)).data,
    deleteSubscription: async (subscriptionId) => (await api.delete(`/agent/subscriptions/${subscriptionId}`)).data,
    listSessions: async (params = {}) => (await api.get('/agent/sessions', { params: compactParams(params) })).data,
    createSession: async (payload) => (await api.post('/agent/sessions', payload)).data,
    getSession: async (sessionId) => (await api.get(`/agent/sessions/${sessionId}`)).data,
    listSessionMessages: async (sessionId, params = {}) =>
        (await api.get(`/agent/sessions/${sessionId}/messages`, { params: compactParams(params) })).data,
    createMessage: async (sessionId, payload) => (await api.post(`/agent/sessions/${sessionId}/messages`, payload)).data,
    listRuns: async (params = {}) => (await api.get('/agent/runs', { params: compactParams(params) })).data,
    createRun: async (payload) => (await api.post('/agent/runs', payload)).data,
    getRun: async (runId) => (await api.get(`/agent/runs/${runId}`)).data,
    listApprovals: async (params = {}) => (await api.get('/agent/approvals', { params: compactParams(params) })).data,
    answerApproval: async (approvalId, payload) => (await api.post(`/agent/approvals/${approvalId}/answer`, payload)).data,
    listScheduledTasks: async (params = {}) =>
        (await api.get('/agent/scheduled-tasks', { params: compactParams(params) })).data,
    updateScheduledTask: async (taskId, payload) => (await api.put(`/agent/scheduled-tasks/${taskId}`, payload)).data,
    triggerScheduledTask: async (taskId) => (await api.post(`/agent/scheduled-tasks/${taskId}/trigger`)).data,
    bootstrapDefaults: async (params = {}) =>
        (await api.post('/agent/scheduled-tasks/bootstrap-defaults', null, { params: compactParams(params) })).data,
};
