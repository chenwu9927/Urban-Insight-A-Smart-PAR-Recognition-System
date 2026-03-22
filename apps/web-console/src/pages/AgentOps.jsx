import { startTransition, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import {
    Activity,
    Bot,
    Check,
    Clock3,
    LoaderCircle,
    MessageSquare,
    PauseCircle,
    PlayCircle,
    RefreshCw,
    Search,
    Send,
    ShieldAlert,
    TimerReset,
    WandSparkles,
    X,
} from 'lucide-react';
import { agentApi } from '../lib/api';

const POLL_INTERVAL_MS = 3000;
const LIVE_TICK_MS = 1000;
const TOAST_TTL_MS = 7000;
const APPROVAL_URGENT_MINUTES = 10;
const ALERT_PREFS_STORAGE_KEY = 'agent-console-alert-prefs';
const EMPTY_ITEMS = [];

const COUNT_CARDS = [
    { key: 'active_runs', label: 'Active Runs', icon: Activity, tone: 'blue' },
    { key: 'queued_runs', label: 'Queued', icon: PlayCircle, tone: 'amber' },
    { key: 'pending_approvals', label: 'Approvals', icon: ShieldAlert, tone: 'rose' },
    { key: 'enabled_scheduled_tasks', label: 'Patrol Plans', icon: TimerReset, tone: 'teal' },
];

function formatLoopState(loop) {
    if (!loop?.enabled) return 'disabled';
    if (loop.thread_alive) return 'alive';
    if (loop.last_error) return 'error';
    return 'starting';
}

const SESSION_SOURCE_FILTERS = [
    { key: 'all', label: 'All' },
    { key: 'web', label: 'Web' },
    { key: 'email', label: 'Email' },
    { key: 'scheduled_task', label: 'Patrol' },
];

const RUN_FILTERS = [
    { key: 'all', label: 'All' },
    { key: 'active', label: 'Active' },
    { key: 'completed', label: 'Completed' },
    { key: 'failed', label: 'Failed' },
];

const SUBSCRIPTION_SEVERITY_OPTIONS = [
    { key: 'warning', label: 'Warning+' },
    { key: 'critical', label: 'Critical Only' },
    { key: 'info', label: 'All Alerts' },
];

const toneClassMap = {
    blue: 'is-blue',
    amber: 'is-amber',
    rose: 'is-rose',
    teal: 'is-teal',
    slate: 'is-slate',
    emerald: 'is-emerald',
};

const statusToneMap = {
    queued: 'amber',
    claimed: 'blue',
    running: 'blue',
    waiting_approval: 'rose',
    waiting_input: 'amber',
    completed: 'emerald',
    failed: 'rose',
    cancelled: 'slate',
    expired: 'slate',
    active: 'blue',
    approved: 'emerald',
    rejected: 'rose',
    pending: 'amber',
};

const severityToneMap = {
    info: 'blue',
    warning: 'amber',
    critical: 'rose',
};

function getAlertTone(alert) {
    if (!alert) return 'slate';
    if (alert.status === 'resolved') return 'emerald';
    return severityToneMap[alert.severity] || 'amber';
}

function formatDateTime(value) {
    if (!value) return '--';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '--';
    return date.toLocaleString();
}

function formatRelative(value) {
    if (!value) return '--';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '--';
    const diffMs = date.getTime() - Date.now();
    const diffMinutes = Math.round(diffMs / 60000);
    if (Math.abs(diffMinutes) < 1) return 'just now';
    if (Math.abs(diffMinutes) < 60) return `${Math.abs(diffMinutes)} min ${diffMinutes >= 0 ? 'later' : 'ago'}`;
    const diffHours = Math.round(diffMinutes / 60);
    if (Math.abs(diffHours) < 24) return `${Math.abs(diffHours)} h ${diffHours >= 0 ? 'later' : 'ago'}`;
    const diffDays = Math.round(diffHours / 24);
    return `${Math.abs(diffDays)} d ${diffDays >= 0 ? 'later' : 'ago'}`;
}

function formatDuration(startAt, endAt) {
    if (!startAt) return '--';
    const started = new Date(startAt);
    const ended = endAt ? new Date(endAt) : new Date();
    if (Number.isNaN(started.getTime()) || Number.isNaN(ended.getTime())) return '--';
    const diffMs = Math.max(0, ended.getTime() - started.getTime());
    const diffMinutes = Math.round(diffMs / 60000);
    if (diffMinutes < 1) return '<1 min';
    if (diffMinutes < 60) return `${diffMinutes} min`;
    const hours = Math.floor(diffMinutes / 60);
    const minutes = diffMinutes % 60;
    return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
}

function formatCountdown(value, nowMs) {
    if (!value) return 'No deadline';
    const deadline = new Date(value);
    if (Number.isNaN(deadline.getTime())) return 'No deadline';
    const diffMs = deadline.getTime() - nowMs;
    if (diffMs <= 0) return 'Expired';
    const diffMinutes = Math.ceil(diffMs / 60000);
    if (diffMinutes < 60) return `${diffMinutes} min left`;
    const hours = Math.floor(diffMinutes / 60);
    const minutes = diffMinutes % 60;
    return minutes ? `${hours} h ${minutes} min left` : `${hours} h left`;
}

function isApprovalUrgent(approval, nowMs) {
    if (!approval?.expires_at) return false;
    const deadline = new Date(approval.expires_at);
    if (Number.isNaN(deadline.getTime())) return false;
    const diffMs = deadline.getTime() - nowMs;
    return diffMs > 0 && diffMs <= APPROVAL_URGENT_MINUTES * 60 * 1000;
}

function getTaskAnomaly(task) {
    if (!task) return '';
    if (task.last_run_status === 'failed') return task.last_error || 'Last patrol failed';
    if (task.last_error) return task.last_error;
    return '';
}

function getDesktopPermission() {
    if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported';
    return window.Notification.permission;
}

function loadAlertPrefs() {
    if (typeof window === 'undefined') {
        return { desktop: false, sound: false };
    }
    try {
        const raw = window.localStorage.getItem(ALERT_PREFS_STORAGE_KEY);
        if (!raw) return { desktop: false, sound: false };
        const parsed = JSON.parse(raw);
        return {
            desktop: Boolean(parsed?.desktop),
            sound: Boolean(parsed?.sound),
        };
    } catch {
        return { desktop: false, sound: false };
    }
}

function shouldEscalateToast(tone) {
    return tone === 'rose' || tone === 'amber';
}

function matchesExactFilter(value, filter) {
    if (filter === 'all') return true;
    return String(value || '').trim() === filter;
}

function collectOptionValues(values) {
    return Array.from(new Set(values.map((item) => String(item || '').trim()).filter(Boolean))).sort((left, right) =>
        left.localeCompare(right),
    );
}

function getSessionScope(session) {
    return {
        siteId: String(session?.site_id || '').trim(),
        cameraId: String(session?.camera_id || '').trim(),
    };
}

function getTaskScope(task, sessionMap) {
    const sessionScope = getSessionScope(sessionMap.get(task?.session_id));
    if (task?.scope_type === 'site') {
        return { siteId: String(task.scope_id || '').trim(), cameraId: sessionScope.cameraId };
    }
    if (task?.scope_type === 'camera') {
        return { siteId: sessionScope.siteId, cameraId: String(task.scope_id || '').trim() };
    }
    return sessionScope;
}

function getRunScope(run, sessionMap, taskMap) {
    const sessionScope = getSessionScope(sessionMap.get(run?.session_id));
    if (!run?.scheduled_task_id) {
        return sessionScope;
    }
    const taskScope = getTaskScope(taskMap.get(run.scheduled_task_id), sessionMap);
    return {
        siteId: sessionScope.siteId || taskScope.siteId,
        cameraId: sessionScope.cameraId || taskScope.cameraId,
    };
}

function getRunRisk(run, taskMap) {
    const paramsRisk = run?.input_payload?.params?.risk_level;
    const directRisk = run?.input_payload?.risk_level;
    const taskRisk = taskMap.get(run?.scheduled_task_id)?.risk_profile;
    return String(paramsRisk || directRisk || taskRisk || '').trim();
}

function matchesScopeFilters(scope, siteFilter, cameraFilter) {
    return matchesExactFilter(scope?.siteId, siteFilter) && matchesExactFilter(scope?.cameraId, cameraFilter);
}

function getMessageText(message) {
    if (!message) return '';
    const content = message.content;
    if (typeof content === 'string') return content;
    if (content && typeof content.text === 'string' && content.text.trim()) return content.text.trim();
    if (content && typeof content.error_message === 'string' && content.error_message.trim()) return content.error_message.trim();
    if (content && content.answer) return String(content.answer);
    if (content && content.output_payload) return JSON.stringify(content.output_payload, null, 2);
    if (content) return JSON.stringify(content, null, 2);
    return '';
}

function getRunAction(run) {
    return run?.input_payload?.action || (run?.schedule_mode === 'scheduled' ? 'scheduled.run' : 'chat.message');
}

function getSessionTitle(session) {
    return session?.title?.trim() || `Session ${session?.id?.slice(0, 8) || ''}`;
}

function sortSessions(items) {
    return [...items].sort((left, right) => {
        const leftValue = new Date(left.last_run_at || left.updated_at || 0).getTime();
        const rightValue = new Date(right.last_run_at || right.updated_at || 0).getTime();
        return rightValue - leftValue;
    });
}

function matchesRunFilter(run, filter) {
    if (filter === 'active') return ['queued', 'claimed', 'running', 'waiting_approval', 'waiting_input'].includes(run.status);
    if (filter === 'completed') return run.status === 'completed';
    if (filter === 'failed') return run.status === 'failed';
    return true;
}

function formatJson(value) {
    if (value === null || value === undefined) return '--';
    if (typeof value === 'string') return value;
    try {
        return JSON.stringify(value, null, 2);
    } catch {
        return String(value);
    }
}

function refreshSelectedDetail(current, { approvals, tasks, alerts }) {
    if (!current?.data?.id) return current;
    if (current.type === 'approval') {
        const approval = approvals.find((item) => item.id === current.data.id);
        return approval ? { type: 'approval', data: approval } : current;
    }
    if (current.type === 'task') {
        const task = tasks.find((item) => item.id === current.data.id);
        return task ? { type: 'task', data: task } : current;
    }
    if (current.type === 'alert') {
        const alert = alerts.find((item) => item.id === current.data.id);
        return alert ? { type: 'alert', data: alert } : current;
    }
    return current;
}

function DetailMeta({ label, value }) {
    return (
        <div className="agent-detail-item">
            <span>{label}</span>
            <strong>{value || '--'}</strong>
        </div>
    );
}

const AgentOps = ({ user }) => {
    const [overview, setOverview] = useState(null);
    const [runtimeStatus, setRuntimeStatus] = useState(null);
    const [sessions, setSessions] = useState([]);
    const [scheduledTasks, setScheduledTasks] = useState([]);
    const [approvalRecords, setApprovalRecords] = useState([]);
    const [runtimeAlerts, setRuntimeAlerts] = useState([]);
    const [subscriptions, setSubscriptions] = useState([]);
    const [patrolRuns, setPatrolRuns] = useState([]);
    const [selectedSessionId, setSelectedSessionId] = useState('');
    const [messages, setMessages] = useState([]);
    const [sessionRuns, setSessionRuns] = useState([]);
    const [selectedDetail, setSelectedDetail] = useState(null);
    const [loading, setLoading] = useState(true);
    const [conversationLoading, setConversationLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [bootstrapping, setBootstrapping] = useState(false);
    const [approvalSubmittingId, setApprovalSubmittingId] = useState('');
    const [taskSubmittingId, setTaskSubmittingId] = useState('');
    const [subscriptionSubmittingId, setSubscriptionSubmittingId] = useState('');
    const [draft, setDraft] = useState('');
    const [subscriptionEmail, setSubscriptionEmail] = useState('');
    const [subscriptionSeverity, setSubscriptionSeverity] = useState('warning');
    const [error, setError] = useState('');
    const [lastSyncAt, setLastSyncAt] = useState('');
    const [sessionQuery, setSessionQuery] = useState('');
    const [sessionSourceFilter, setSessionSourceFilter] = useState('all');
    const [runFilter, setRunFilter] = useState('all');
    const [siteFilter, setSiteFilter] = useState('all');
    const [cameraFilter, setCameraFilter] = useState('all');
    const [riskFilter, setRiskFilter] = useState('all');
    const [alertPrefs, setAlertPrefs] = useState(() => loadAlertPrefs());
    const [notificationPermission, setNotificationPermission] = useState(() => getDesktopPermission());
    const [liveNow, setLiveNow] = useState(() => Date.now());
    const [toastItems, setToastItems] = useState([]);
    const [recentRunUpdates, setRecentRunUpdates] = useState({});
    const messageListRef = useRef(null);
    const audioContextRef = useRef(null);
    const snapshotRef = useRef({
        hydrated: false,
        runs: new Map(),
        approvals: new Map(),
        alerts: new Map(),
        patrolRuns: new Map(),
        urgentApprovals: new Set(),
        taskAnomalies: new Set(),
    });
    const toastKeyRef = useRef(new Set());
    const deferredSessionQuery = useDeferredValue(sessionQuery);

    const selectedSession = useMemo(
        () => sessions.find((item) => item.id === selectedSessionId) || null,
        [sessions, selectedSessionId],
    );
    const sessionMap = useMemo(() => new Map(sessions.map((session) => [session.id, session])), [sessions]);
    const taskMap = useMemo(() => new Map(scheduledTasks.map((task) => [task.id, task])), [scheduledTasks]);

    const activeRuns = overview?.active_runs || EMPTY_ITEMS;
    const recentRuns = overview?.recent_runs || EMPTY_ITEMS;
    const pendingApprovals = useMemo(
        () => approvalRecords.filter((item) => item.status === 'pending'),
        [approvalRecords],
    );
    const siteOptions = useMemo(
        () =>
            collectOptionValues([
                ...sessions.map((session) => session.site_id),
                ...scheduledTasks.filter((task) => task.scope_type === 'site').map((task) => task.scope_id),
            ]),
        [scheduledTasks, sessions],
    );
    const cameraOptions = useMemo(
        () =>
            collectOptionValues([
                ...sessions.map((session) => session.camera_id),
                ...scheduledTasks.filter((task) => task.scope_type === 'camera').map((task) => task.scope_id),
            ]),
        [scheduledTasks, sessions],
    );
    const riskOptions = useMemo(
        () =>
            collectOptionValues([
                ...scheduledTasks.map((task) => task.risk_profile),
                ...approvalRecords.map((approval) => approval.risk_level),
                ...recentRuns.map((run) => getRunRisk(run, taskMap)),
                ...activeRuns.map((run) => getRunRisk(run, taskMap)),
            ]),
        [activeRuns, approvalRecords, recentRuns, scheduledTasks, taskMap],
    );
    const filteredSessions = useMemo(() => {
        const query = deferredSessionQuery.trim().toLowerCase();
        return sessions.filter((session) => {
            const matchesSource = sessionSourceFilter === 'all' || session.source === sessionSourceFilter;
            if (!matchesSource) return false;
            if (!matchesScopeFilters(getSessionScope(session), siteFilter, cameraFilter)) return false;
            if (!query) return true;
            const haystack = [session.title, session.kind, session.source, session.status, session.id]
                .filter(Boolean)
                .join(' ')
                .toLowerCase();
            return haystack.includes(query);
        });
    }, [sessions, deferredSessionQuery, sessionSourceFilter, siteFilter, cameraFilter]);
    const filteredActiveRuns = useMemo(
        () =>
            activeRuns.filter((run) => {
                const scope = getRunScope(run, sessionMap, taskMap);
                return matchesScopeFilters(scope, siteFilter, cameraFilter) && matchesExactFilter(getRunRisk(run, taskMap), riskFilter);
            }),
        [activeRuns, sessionMap, taskMap, siteFilter, cameraFilter, riskFilter],
    );
    const filteredPendingApprovals = useMemo(
        () =>
            pendingApprovals.filter((approval) => {
                const scope = getSessionScope(sessionMap.get(approval.session_id));
                return matchesScopeFilters(scope, siteFilter, cameraFilter) && matchesExactFilter(approval.risk_level, riskFilter);
            }),
        [pendingApprovals, sessionMap, siteFilter, cameraFilter, riskFilter],
    );
    const filteredScheduledTasks = useMemo(
        () =>
            scheduledTasks.filter((task) => {
                const scope = getTaskScope(task, sessionMap);
                return matchesScopeFilters(scope, siteFilter, cameraFilter) && matchesExactFilter(task.risk_profile, riskFilter);
            }),
        [scheduledTasks, sessionMap, siteFilter, cameraFilter, riskFilter],
    );
    const activeSessionRuns = useMemo(
        () => filteredActiveRuns.filter((run) => (selectedSessionId ? run.session_id === selectedSessionId : true)),
        [filteredActiveRuns, selectedSessionId],
    );
    const urgentApprovalCount = useMemo(
        () => filteredPendingApprovals.filter((approval) => isApprovalUrgent(approval, liveNow)).length,
        [filteredPendingApprovals, liveNow],
    );
    const patrolAnomalyCount = useMemo(
        () => filteredScheduledTasks.filter((task) => Boolean(getTaskAnomaly(task))).length,
        [filteredScheduledTasks],
    );
    const openRuntimeAlertCount = useMemo(
        () => runtimeAlerts.filter((alert) => alert.status === 'open').length,
        [runtimeAlerts],
    );
    const desktopAlertLabel = useMemo(() => {
        if (notificationPermission === 'unsupported') return 'Desktop Unsupported';
        if (notificationPermission === 'denied') return 'Desktop Blocked';
        if (notificationPermission === 'granted') return alertPrefs.desktop ? 'Desktop Alerts On' : 'Desktop Alerts Off';
        return 'Enable Desktop Alerts';
    }, [alertPrefs.desktop, notificationPermission]);

    const dismissToast = useCallback((toastId, toastKey) => {
        setToastItems((current) => current.filter((item) => item.id !== toastId));
        if (toastKey) {
            toastKeyRef.current.delete(toastKey);
        }
    }, []);

    const playAlertTone = useCallback((tone = 'blue') => {
        if (typeof window === 'undefined') return;
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return;

        try {
            if (!audioContextRef.current) {
                audioContextRef.current = new AudioContextClass();
            }
            const audioContext = audioContextRef.current;
            if (audioContext.state === 'suspended') {
                audioContext.resume().catch(() => {});
            }

            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            const now = audioContext.currentTime;
            const frequency = tone === 'rose' ? 880 : tone === 'amber' ? 720 : 540;

            oscillator.type = tone === 'rose' ? 'sawtooth' : 'sine';
            oscillator.frequency.setValueAtTime(frequency, now);
            gainNode.gain.setValueAtTime(0.0001, now);
            gainNode.gain.linearRampToValueAtTime(0.08, now + 0.02);
            gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.28);
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            oscillator.start(now);
            oscillator.stop(now + 0.3);
        } catch {
            // ignore sound failures when the browser blocks autoplay
        }
    }, []);

    const fireDesktopNotification = useCallback(({ tone, title, body, key }) => {
        if (typeof window === 'undefined') return;
        if (!alertPrefs.desktop || notificationPermission !== 'granted' || !('Notification' in window)) return;
        if (!document.hidden && !shouldEscalateToast(tone)) return;

        try {
            new window.Notification(title, {
                body,
                tag: key,
                requireInteraction: tone === 'rose',
            });
        } catch {
            // ignore notification failures
        }
    }, [alertPrefs.desktop, notificationPermission]);

    const pushToast = useCallback(({ key, tone = 'blue', title, body }) => {
        const toastKey = key || `${tone}:${title}:${body}`;
        if (toastKeyRef.current.has(toastKey)) return;
        toastKeyRef.current.add(toastKey);
        const toastId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        setToastItems((current) => [...current.slice(-3), { id: toastId, tone, title, body, key: toastKey }]);
        if (alertPrefs.sound && (shouldEscalateToast(tone) || document.hidden)) {
            playAlertTone(tone);
        }
        fireDesktopNotification({ tone, title, body, key: toastKey });
        window.setTimeout(() => dismissToast(toastId, toastKey), TOAST_TTL_MS);
    }, [alertPrefs.sound, dismissToast, fireDesktopNotification, playAlertTone]);

    const markRunUpdated = useCallback((runId) => {
        if (!runId) return;
        setRecentRunUpdates((current) => ({ ...current, [runId]: Date.now() }));
        window.setTimeout(() => {
            setRecentRunUpdates((current) => {
                if (!current[runId]) return current;
                const next = { ...current };
                delete next[runId];
                return next;
            });
        }, 4500);
    }, []);

    const processRealtimeSignals = useCallback((data) => {
        const allRuns = [...(data.overviewData?.active_runs || []), ...(data.overviewData?.recent_runs || []), ...(data.patrolRunData || [])];
        const dedupedRuns = Array.from(new Map(allRuns.map((run) => [run.id, run])).values());
        const nextRunMap = new Map(dedupedRuns.map((run) => [run.id, { status: run.status, title: run.session_title || getRunAction(run) }]));
        const nextApprovalMap = new Map((data.approvalData || []).map((approval) => [approval.id, approval]));
        const nextAlertMap = new Map((data.alertData || []).map((alert) => [alert.id, alert]));
        const nextPatrolMap = new Map((data.patrolRunData || []).map((run) => [run.id, run]));
        const nextTaskAnomalies = new Set(
            (data.scheduledTaskData || [])
                .filter((task) => Boolean(getTaskAnomaly(task)))
                .map((task) => task.id),
        );

        if (!snapshotRef.current.hydrated) {
            snapshotRef.current = {
                hydrated: true,
                runs: nextRunMap,
                approvals: nextApprovalMap,
                alerts: nextAlertMap,
                patrolRuns: nextPatrolMap,
                urgentApprovals: new Set(
                    (data.approvalData || [])
                        .filter((approval) => approval.status === 'pending' && isApprovalUrgent(approval, Date.now()))
                        .map((approval) => approval.id),
                ),
                taskAnomalies: nextTaskAnomalies,
            };
            return;
        }

        dedupedRuns.forEach((run) => {
            const previous = snapshotRef.current.runs.get(run.id);
            if (previous && previous.status !== run.status) {
                markRunUpdated(run.id);
                pushToast({
                    key: `run:${run.id}:${run.status}`,
                    tone: run.status === 'failed' ? 'rose' : run.status === 'completed' ? 'emerald' : 'blue',
                    title: 'Run status changed',
                    body: `${run.session_title || getRunAction(run)} is now ${run.status}.`,
                });
            }
        });

        (data.approvalData || []).forEach((approval) => {
            const previous = snapshotRef.current.approvals.get(approval.id);
            if (!previous && approval.status === 'pending') {
                pushToast({
                    key: `approval:new:${approval.id}`,
                    tone: 'amber',
                    title: 'Approval required',
                    body: `${approval.tool_name} needs a decision.`,
                });
            } else if (previous && previous.status !== approval.status) {
                pushToast({
                    key: `approval:${approval.id}:${approval.status}`,
                    tone: approval.status === 'approved' ? 'emerald' : approval.status === 'rejected' ? 'rose' : 'blue',
                    title: 'Approval updated',
                    body: `${approval.tool_name} is now ${approval.status}.`,
                });
            }

            if (approval.status === 'pending' && isApprovalUrgent(approval, Date.now()) && !snapshotRef.current.urgentApprovals.has(approval.id)) {
                pushToast({
                    key: `approval:urgent:${approval.id}`,
                    tone: 'rose',
                    title: 'Approval expiring soon',
                    body: `${approval.tool_name} expires in less than ${APPROVAL_URGENT_MINUTES} minutes.`,
                });
            }
        });

        (data.alertData || []).forEach((alert) => {
            const previous = snapshotRef.current.alerts.get(alert.id);
            if (!previous && alert.status === 'open') {
                pushToast({
                    key: `runtime-alert:new:${alert.id}`,
                    tone: getAlertTone(alert),
                    title: 'Runtime alert',
                    body: alert.summary,
                });
            } else if (previous && previous.status !== alert.status) {
                pushToast({
                    key: `runtime-alert:${alert.id}:${alert.status}`,
                    tone: getAlertTone(alert),
                    title: alert.status === 'resolved' ? 'Runtime recovered' : 'Runtime alert updated',
                    body: alert.status === 'resolved' ? `${alert.scope_id || alert.source_rule} recovered.` : alert.summary,
                });
            }
        });

        (data.patrolRunData || []).forEach((run) => {
            const previous = snapshotRef.current.patrolRuns.get(run.id);
            if ((!previous && run.status === 'failed') || (previous && previous.status !== run.status && run.status === 'failed')) {
                pushToast({
                    key: `patrol-run:${run.id}:failed`,
                    tone: 'rose',
                    title: 'Patrol failed',
                    body: run.result_summary || run.last_error || `${getRunAction(run)} failed.`,
                });
            }
        });

        (data.scheduledTaskData || []).forEach((task) => {
            const anomaly = getTaskAnomaly(task);
            if (anomaly && !snapshotRef.current.taskAnomalies.has(task.id)) {
                pushToast({
                    key: `task-anomaly:${task.id}`,
                    tone: 'rose',
                    title: 'Patrol anomaly detected',
                    body: `${task.name}: ${anomaly}`,
                });
            }
        });

        snapshotRef.current = {
            hydrated: true,
            runs: nextRunMap,
            approvals: nextApprovalMap,
            alerts: nextAlertMap,
            patrolRuns: nextPatrolMap,
            urgentApprovals: new Set(
                (data.approvalData || [])
                    .filter((approval) => approval.status === 'pending' && isApprovalUrgent(approval, Date.now()))
                    .map((approval) => approval.id),
            ),
            taskAnomalies: nextTaskAnomalies,
        };
    }, [markRunUpdated, pushToast]);

    const pullDashboardData = useCallback(async () => {
        const [overviewData, sessionData, scheduledTaskData, approvalData, patrolRunData, runtimeStatusData, alertData, subscriptionData] = await Promise.all([
            agentApi.overview(),
            agentApi.listSessions({ limit: 50 }),
            agentApi.listScheduledTasks({ limit: 20 }),
            agentApi.listApprovals({ limit: 20 }),
            agentApi.listRuns({ schedule_mode: 'scheduled', limit: 20 }),
            agentApi.runtimeStatus().catch(() => null),
            agentApi.listAlerts({ scope_type: 'service_loop', limit: 20 }),
            agentApi.listSubscriptions({ channel: 'email', limit: 20 }),
        ]);

        return {
            overviewData,
            runtimeStatusData,
            alertData,
            subscriptionData,
            sessionData: sortSessions(sessionData),
            scheduledTaskData,
            approvalData,
            patrolRunData,
        };
    }, []);

    useEffect(() => {
        if (!messageListRef.current) return;
        messageListRef.current.scrollTop = messageListRef.current.scrollHeight;
    }, [messages]);

    useEffect(() => {
        const intervalId = window.setInterval(() => {
            setLiveNow(Date.now());
        }, LIVE_TICK_MS);
        return () => window.clearInterval(intervalId);
    }, []);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        window.localStorage.setItem(ALERT_PREFS_STORAGE_KEY, JSON.stringify(alertPrefs));
    }, [alertPrefs]);

    useEffect(() => {
        setNotificationPermission(getDesktopPermission());
    }, []);

    useEffect(() => {
        if (notificationPermission !== 'granted' && alertPrefs.desktop) {
            setAlertPrefs((current) => ({ ...current, desktop: false }));
        }
    }, [alertPrefs.desktop, notificationPermission]);

    useEffect(() => {
        let cancelled = false;

        const loadOverviewBundle = async ({ silent = false } = {}) => {
            if (!silent) setLoading(true);
            try {
                const data = await pullDashboardData();
                if (cancelled) return;
                processRealtimeSignals(data);
                startTransition(() => {
                    setOverview(data.overviewData);
                    setRuntimeStatus(data.runtimeStatusData);
                    setSessions(data.sessionData);
                    setScheduledTasks(data.scheduledTaskData);
                    setApprovalRecords(data.approvalData);
                    setRuntimeAlerts(data.alertData);
                    setSubscriptions(data.subscriptionData);
                    setPatrolRuns(data.patrolRunData);
                    setSelectedSessionId((current) => current || data.sessionData[0]?.id || '');
                    setSelectedDetail((current) =>
                        refreshSelectedDetail(current, {
                            approvals: data.approvalData,
                            tasks: data.scheduledTaskData,
                            alerts: data.alertData,
                        }),
                    );
                    setLastSyncAt(new Date().toISOString());
                    setError('');
                });
            } catch {
                if (!cancelled) setError('Failed to load agent overview.');
            } finally {
                if (!cancelled && !silent) setLoading(false);
            }
        };

        loadOverviewBundle();
        const intervalId = window.setInterval(() => {
            loadOverviewBundle({ silent: true });
        }, POLL_INTERVAL_MS);

        return () => {
            cancelled = true;
            window.clearInterval(intervalId);
        };
    }, [processRealtimeSignals, pullDashboardData]);

    useEffect(() => {
        if (!selectedSessionId) {
            setMessages([]);
            setSessionRuns([]);
            return undefined;
        }

        let cancelled = false;

        const loadConversation = async ({ silent = false } = {}) => {
            if (!silent) setConversationLoading(true);
            try {
                const [messageData, runData] = await Promise.all([
                    agentApi.listSessionMessages(selectedSessionId, { limit: 200 }),
                    agentApi.listRuns({ session_id: selectedSessionId, limit: 50 }),
                ]);
                if (cancelled) return;
                startTransition(() => {
                    setMessages(messageData);
                    setSessionRuns(runData);
                });
            } catch {
                if (!cancelled) setError('Failed to load conversation details.');
            } finally {
                if (!cancelled && !silent) setConversationLoading(false);
            }
        };

        loadConversation();
        const intervalId = window.setInterval(() => {
            loadConversation({ silent: true });
        }, POLL_INTERVAL_MS);

        return () => {
            cancelled = true;
            window.clearInterval(intervalId);
        };
    }, [selectedSessionId]);

    useEffect(() => {
        if (selectedDetail?.type !== 'run' || !selectedDetail?.data?.id) return undefined;

        let cancelled = false;

        const syncRunDetail = async () => {
            try {
                const run = await agentApi.getRun(selectedDetail.data.id);
                if (!cancelled) {
                    setSelectedDetail((current) =>
                        current?.type === 'run' && current.data.id === run.id ? { type: 'run', data: run } : current,
                    );
                }
            } catch {
                // keep current snapshot when detail refresh fails
            }
        };

        syncRunDetail();
        const intervalId = window.setInterval(syncRunDetail, POLL_INTERVAL_MS);
        return () => {
            cancelled = true;
            window.clearInterval(intervalId);
        };
    }, [selectedDetail?.type, selectedDetail?.data?.id]);

    const handleRefresh = async () => {
        setLoading(true);
        try {
            const data = await pullDashboardData();
            processRealtimeSignals(data);
            setOverview(data.overviewData);
            setRuntimeStatus(data.runtimeStatusData);
            setSessions(data.sessionData);
            setScheduledTasks(data.scheduledTaskData);
            setApprovalRecords(data.approvalData);
            setRuntimeAlerts(data.alertData);
            setSubscriptions(data.subscriptionData);
            setPatrolRuns(data.patrolRunData);
            if (!selectedSessionId && data.sessionData[0]?.id) {
                setSelectedSessionId(data.sessionData[0].id);
            }
            setSelectedDetail((current) =>
                refreshSelectedDetail(current, {
                    approvals: data.approvalData,
                    tasks: data.scheduledTaskData,
                    alerts: data.alertData,
                }),
            );
            setLastSyncAt(new Date().toISOString());
            setError('');
        } catch {
            setError('Failed to refresh agent data.');
        } finally {
            setLoading(false);
        }
    };

    const handleNewSession = () => {
        setSelectedSessionId('');
        setMessages([]);
        setSessionRuns([]);
        setDraft('');
        setError('');
    };

    const handleBootstrap = async () => {
        setBootstrapping(true);
        try {
            await agentApi.bootstrapDefaults();
            await handleRefresh();
        } catch {
            setError('Failed to bootstrap default patrol plans.');
        } finally {
            setBootstrapping(false);
        }
    };

    const handleDesktopAlertsToggle = async () => {
        const permission = getDesktopPermission();
        if (permission === 'unsupported') {
            setError('This browser does not support desktop notifications.');
            return;
        }

        if (permission === 'granted') {
            setAlertPrefs((current) => ({ ...current, desktop: !current.desktop }));
            return;
        }

        if (permission === 'denied') {
            setError('Desktop notifications are blocked in this browser. Please allow them in browser settings first.');
            return;
        }

        try {
            const nextPermission = await window.Notification.requestPermission();
            setNotificationPermission(nextPermission);
            if (nextPermission === 'granted') {
                setAlertPrefs((current) => ({ ...current, desktop: true }));
                pushToast({
                    key: 'desktop-alerts-enabled',
                    tone: 'emerald',
                    title: 'Desktop alerts enabled',
                    body: 'The browser will now surface important agent events even when the tab is in the background.',
                });
            } else {
                setError('Desktop notifications were not granted.');
            }
        } catch {
            setError('Failed to request desktop notification permission.');
        }
    };

    const handleSoundToggle = () => {
        const nextEnabled = !alertPrefs.sound;
        setAlertPrefs((current) => ({ ...current, sound: nextEnabled }));
        if (nextEnabled) {
            playAlertTone('amber');
        }
    };

    const handleResetOpsFilters = () => {
        setSiteFilter('all');
        setCameraFilter('all');
        setRiskFilter('all');
    };

    const handleSend = async () => {
        const prompt = draft.trim();
        if (!prompt || sending) return;
        setSending(true);
        try {
            let sessionId = selectedSessionId;
            if (!sessionId) {
                const newSession = await agentApi.createSession({
                    kind: 'command',
                    title: prompt.slice(0, 72),
                    status: 'active',
                    source: 'web',
                    owner_user_id: user?.id || null,
                });
                sessionId = newSession.id;
                setSelectedSessionId(sessionId);
            }

            const run = await agentApi.createRun({
                session_id: sessionId,
                schedule_mode: 'immediate',
                permission_mode: 'default',
                prompt,
            });

            setDraft('');
            setSelectedDetail({ type: 'run', data: run });

            const [messageData, runData, dashboardData] = await Promise.all([
                agentApi.listSessionMessages(sessionId, { limit: 200 }),
                agentApi.listRuns({ session_id: sessionId, limit: 50 }),
                pullDashboardData(),
            ]);
            processRealtimeSignals(dashboardData);

            startTransition(() => {
                setMessages(messageData);
                setSessionRuns(runData);
                setOverview(dashboardData.overviewData);
                setRuntimeStatus(dashboardData.runtimeStatusData);
                setSessions(dashboardData.sessionData);
                setScheduledTasks(dashboardData.scheduledTaskData);
                setApprovalRecords(dashboardData.approvalData);
                setRuntimeAlerts(dashboardData.alertData);
                setSubscriptions(dashboardData.subscriptionData);
                setPatrolRuns(dashboardData.patrolRunData);
                setLastSyncAt(new Date().toISOString());
                setError('');
            });
        } catch {
            setError('Failed to send message to agent.');
        } finally {
            setSending(false);
        }
    };

    const handleApprovalDecision = async (approvalId, status) => {
        if (!approvalId || approvalSubmittingId) return;
        setApprovalSubmittingId(approvalId);
        try {
            const approval = await agentApi.answerApproval(approvalId, {
                status,
                answered_by_user_id: user?.id || null,
                answers: { source: 'web', decided_at: new Date().toISOString() },
            });
            setSelectedDetail((current) =>
                current?.type === 'approval' && current.data.id === approval.id ? { type: 'approval', data: approval } : current,
            );
            await handleRefresh();
        } catch {
            setError(`Failed to ${status === 'approved' ? 'approve' : 'reject'} request.`);
        } finally {
            setApprovalSubmittingId('');
        }
    };

    const handleTaskTrigger = async (taskId) => {
        if (!taskId || taskSubmittingId) return;
        setTaskSubmittingId(`trigger:${taskId}`);
        try {
            const dispatch = await agentApi.triggerScheduledTask(taskId);
            if (dispatch?.session_id) {
                setSelectedSessionId(dispatch.session_id);
            }
            if (dispatch?.run_id) {
                const run = await agentApi.getRun(dispatch.run_id);
                setSelectedDetail({ type: 'run', data: run });
            }
            await handleRefresh();
        } catch {
            setError('Failed to trigger patrol task.');
        } finally {
            setTaskSubmittingId('');
        }
    };

    const handleTaskToggle = async (task) => {
        if (!task?.id || taskSubmittingId) return;
        setTaskSubmittingId(`toggle:${task.id}`);
        try {
            const updatedTask = await agentApi.updateScheduledTask(task.id, { enabled: !task.enabled });
            setSelectedDetail((current) =>
                current?.type === 'task' && current.data.id === updatedTask.id ? { type: 'task', data: updatedTask } : current,
            );
            await handleRefresh();
        } catch {
            setError(`Failed to ${task.enabled ? 'pause' : 'enable'} patrol task.`);
        } finally {
            setTaskSubmittingId('');
        }
    };

    const handleCreateSubscription = async () => {
        const target = subscriptionEmail.trim().toLowerCase();
        if (!target || subscriptionSubmittingId) return;
        setSubscriptionSubmittingId('create');
        try {
            await agentApi.createSubscription({
                channel: 'email',
                target,
                severity_floor: subscriptionSeverity,
                schedule_type: 'realtime',
                enabled: true,
                user_id: user?.id || null,
            });
            setSubscriptionEmail('');
            pushToast({
                key: `subscription:create:${target}`,
                tone: 'emerald',
                title: 'Alert routing updated',
                body: `${target} will now receive runtime alerts.`,
            });
            await handleRefresh();
        } catch {
            setError('Failed to create alert subscription.');
        } finally {
            setSubscriptionSubmittingId('');
        }
    };

    const handleSubscriptionToggle = async (subscription) => {
        if (!subscription?.id || subscriptionSubmittingId) return;
        setSubscriptionSubmittingId(`toggle:${subscription.id}`);
        try {
            await agentApi.updateSubscription(subscription.id, { enabled: !subscription.enabled });
            await handleRefresh();
        } catch {
            setError(`Failed to ${subscription.enabled ? 'pause' : 'enable'} alert subscription.`);
        } finally {
            setSubscriptionSubmittingId('');
        }
    };

    const handleSubscriptionDelete = async (subscriptionId) => {
        if (!subscriptionId || subscriptionSubmittingId) return;
        setSubscriptionSubmittingId(`delete:${subscriptionId}`);
        try {
            await agentApi.deleteSubscription(subscriptionId);
            await handleRefresh();
        } catch {
            setError('Failed to delete alert subscription.');
        } finally {
            setSubscriptionSubmittingId('');
        }
    };

    const openRunDetail = async (runLike) => {
        if (!runLike?.id) return;
        try {
            const run = await agentApi.getRun(runLike.id);
            setSelectedDetail({ type: 'run', data: run });
            if (run.session_id) {
                setSelectedSessionId(run.session_id);
            }
        } catch {
            setError('Failed to load run detail.');
        }
    };

    const openApprovalDetail = (approval) => {
        setSelectedDetail({ type: 'approval', data: approval });
        if (approval?.session_id) {
            setSelectedSessionId(approval.session_id);
        }
    };

    const openTaskDetail = (task) => {
        setSelectedDetail({ type: 'task', data: task });
        if (task?.session_id) {
            setSelectedSessionId(task.session_id);
        }
    };

    const openAlertDetail = (alert) => {
        setSelectedDetail({ type: 'alert', data: alert });
    };

    const runHistory = selectedSessionId ? sessionRuns : recentRuns;
    const filteredRunHistory = runHistory.filter((run) => {
        const scope = getRunScope(run, sessionMap, taskMap);
        return (
            matchesRunFilter(run, runFilter)
            && matchesScopeFilters(scope, siteFilter, cameraFilter)
            && matchesExactFilter(getRunRisk(run, taskMap), riskFilter)
        );
    });
    const runtimeLoop = runtimeStatus?.loops?.runtime || null;
    const schedulerLoop = runtimeStatus?.loops?.scheduler || null;
    const emailLoop = runtimeStatus?.loops?.email || null;
    const nextPatrolTask = filteredScheduledTasks.find((task) => task.enabled && task.next_run_at) || null;
    const consoleSummary = activeSessionRuns[0] || filteredActiveRuns[0] || null;
    const totalLoopRestarts = (runtimeLoop?.restart_count || 0) + (schedulerLoop?.restart_count || 0) + (emailLoop?.restart_count || 0);
    const patrolHistory = patrolRuns.filter((run) => {
        const scope = getRunScope(run, sessionMap, taskMap);
        return matchesScopeFilters(scope, siteFilter, cameraFilter) && matchesExactFilter(getRunRisk(run, taskMap), riskFilter);
    }).slice(0, 8);

    const detailPanel = (() => {
        if (!selectedDetail) return null;

        if (selectedDetail.type === 'run') {
            const run = selectedDetail.data;
            return (
                <>
                    <div className="agent-detail-grid">
                        <DetailMeta label="Status" value={run.status} />
                        <DetailMeta label="Action" value={getRunAction(run)} />
                        <DetailMeta label="Progress" value={`${run.progress ?? 0}%`} />
                        <DetailMeta label="Mode" value={run.schedule_mode} />
                        <DetailMeta label="Worker" value={run.claimed_by} />
                        <DetailMeta label="Duration" value={formatDuration(run.started_at || run.scheduled_at, run.finished_at)} />
                    </div>
                    <section className="agent-detail-section">
                        <h3>Summary</h3>
                        <p>{run.result_summary || run.last_error || 'No summary available.'}</p>
                    </section>
                    <section className="agent-detail-section">
                        <h3>Timeline</h3>
                        <div className="agent-detail-grid">
                            <DetailMeta label="Scheduled" value={formatDateTime(run.scheduled_at)} />
                            <DetailMeta label="Started" value={formatDateTime(run.started_at)} />
                            <DetailMeta label="Heartbeat" value={formatDateTime(run.last_heartbeat_at)} />
                            <DetailMeta label="Finished" value={formatDateTime(run.finished_at)} />
                        </div>
                    </section>
                    <section className="agent-detail-section">
                        <h3>Input Payload</h3>
                        <pre className="agent-json-block">{formatJson(run.input_payload)}</pre>
                    </section>
                    <section className="agent-detail-section">
                        <h3>Output Payload</h3>
                        <pre className="agent-json-block">{formatJson(run.output_payload)}</pre>
                    </section>
                </>
            );
        }

        if (selectedDetail.type === 'approval') {
            const approval = selectedDetail.data;
            return (
                <>
                    <div className="agent-detail-grid">
                        <DetailMeta label="Status" value={approval.status} />
                        <DetailMeta label="Risk" value={approval.risk_level} />
                        <DetailMeta label="Tool" value={approval.tool_name} />
                        <DetailMeta label="Session" value={approval.session_id?.slice(0, 8)} />
                        <DetailMeta label="Created" value={formatDateTime(approval.created_at)} />
                        <DetailMeta label="Expires" value={formatDateTime(approval.expires_at)} />
                    </div>
                    <section className="agent-detail-section">
                        <h3>Reason</h3>
                        <p>{approval.reason || 'No detailed reason provided.'}</p>
                    </section>
                    <section className="agent-detail-section">
                        <h3>Tool Input</h3>
                        <pre className="agent-json-block">{formatJson(approval.tool_input)}</pre>
                    </section>
                    <section className="agent-detail-section">
                        <h3>Decision Context</h3>
                        <pre className="agent-json-block">{formatJson(approval.answers)}</pre>
                    </section>
                </>
            );
        }

        if (selectedDetail.type === 'alert') {
            const alert = selectedDetail.data;
            return (
                <>
                    <div className="agent-detail-grid">
                        <DetailMeta label="Status" value={alert.status} />
                        <DetailMeta label="Severity" value={alert.severity} />
                        <DetailMeta label="Rule" value={alert.source_rule} />
                        <DetailMeta label="Scope" value={alert.scope_id || alert.scope_type || '--'} />
                        <DetailMeta label="Detected" value={formatDateTime(alert.detected_at)} />
                        <DetailMeta label="Updated" value={formatDateTime(alert.updated_at)} />
                    </div>
                    <section className="agent-detail-section">
                        <h3>Summary</h3>
                        <p>{alert.summary || 'No summary available.'}</p>
                    </section>
                    <section className="agent-detail-section">
                        <h3>Evidence</h3>
                        <pre className="agent-json-block">{formatJson(alert.evidence_summary)}</pre>
                    </section>
                    <section className="agent-detail-section">
                        <h3>Alert Payload</h3>
                        <pre className="agent-json-block">{formatJson(alert)}</pre>
                    </section>
                </>
            );
        }

        const task = selectedDetail.data;
        return (
            <>
                <div className="agent-detail-grid">
                    <DetailMeta label="Status" value={task.enabled ? 'enabled' : 'disabled'} />
                    <DetailMeta label="Timezone" value={task.timezone} />
                    <DetailMeta label="Risk" value={task.risk_profile} />
                    <DetailMeta label="Cron" value={task.cron} />
                    <DetailMeta label="Next Run" value={formatDateTime(task.next_run_at)} />
                    <DetailMeta label="Last Run" value={task.last_run_status || '--'} />
                </div>
                <section className="agent-detail-section">
                    <h3>Description</h3>
                    <p>{task.description || 'No description available.'}</p>
                </section>
                <section className="agent-detail-section">
                    <h3>Prompt Template</h3>
                    <pre className="agent-json-block">{formatJson(task.prompt_template)}</pre>
                </section>
                <section className="agent-detail-section">
                    <h3>Task Snapshot</h3>
                    <pre className="agent-json-block">{formatJson(task.config_snapshot)}</pre>
                </section>
            </>
        );
    })();

    return (
        <div className="agent-page">
            <section className="agent-hero">
                <div>
                    <span className="agent-eyebrow">Always-on Operations</span>
                    <h1>Agent Console</h1>
                    <p>
                        Chat with the security agent from the browser, inspect live execution, and review patrol history
                        in one place.
                    </p>
                </div>
                <div className="agent-hero-actions">
                    <button
                        className={`btn-ghost ${alertPrefs.desktop ? 'is-enabled' : ''}`}
                        onClick={handleDesktopAlertsToggle}
                        disabled={notificationPermission === 'unsupported'}
                    >
                        <ShieldAlert size={16} />
                        {desktopAlertLabel}
                    </button>
                    <button className={`btn-ghost ${alertPrefs.sound ? 'is-enabled' : ''}`} onClick={handleSoundToggle}>
                        <Clock3 size={16} />
                        {alertPrefs.sound ? 'Sound On' : 'Sound Off'}
                    </button>
                    <button className="btn-secondary" onClick={handleBootstrap} disabled={bootstrapping}>
                        {bootstrapping ? <LoaderCircle size={16} className="spin" /> : <WandSparkles size={16} />}
                        Bootstrap Patrols
                    </button>
                    <button className="btn-primary" onClick={handleRefresh} disabled={loading}>
                        {loading ? <LoaderCircle size={16} className="spin" /> : <RefreshCw size={16} />}
                        Refresh
                    </button>
                </div>
            </section>

            {error ? <div className="agent-banner error">{error}</div> : null}

            <section className="agent-count-grid">
                {COUNT_CARDS.map(({ key, label, icon: Icon, tone }) => (
                    <article key={key} className="agent-count-card">
                        <div className={`agent-count-icon ${toneClassMap[tone]}`}>
                            <Icon size={20} />
                        </div>
                        <div>
                            <div className="agent-count-label">{label}</div>
                            <div className="agent-count-value">{overview?.counts?.[key] ?? 0}</div>
                        </div>
                    </article>
                ))}
            </section>

            <section className="agent-strip-grid">
                <article className="agent-strip-card">
                    <span className="agent-strip-label">Console State</span>
                    <strong>{loading ? 'Syncing' : urgentApprovalCount || patrolAnomalyCount || openRuntimeAlertCount ? 'Attention' : 'Live'}</strong>
                    <p>
                        Polling every 3 seconds. Last sync {lastSyncAt ? formatRelative(lastSyncAt) : '--'}.
                        Runtime {formatLoopState(runtimeLoop)}, scheduler {formatLoopState(schedulerLoop)}, email {formatLoopState(emailLoop)}.
                    </p>
                    <div className="agent-strip-flags">
                        <span className={`agent-mini-flag ${urgentApprovalCount ? 'is-alert' : ''}`}>{urgentApprovalCount} urgent approvals</span>
                        <span className={`agent-mini-flag ${patrolAnomalyCount ? 'is-alert' : ''}`}>{patrolAnomalyCount} patrol anomalies</span>
                        <span className={`agent-mini-flag ${openRuntimeAlertCount ? 'is-alert' : ''}`}>{openRuntimeAlertCount} runtime alerts</span>
                        <span className="agent-mini-flag">{totalLoopRestarts} loop restarts</span>
                        {runtimeLoop?.last_seen_at ? <span className="agent-mini-flag">Runtime beat {formatRelative(runtimeLoop.last_seen_at)}</span> : null}
                    </div>
                </article>
                <article className="agent-strip-card">
                    <span className="agent-strip-label">Current Focus</span>
                    <strong>{consoleSummary ? (consoleSummary.session_title || getRunAction(consoleSummary)) : 'Idle'}</strong>
                    <p>
                        {consoleSummary
                            ? `${getRunAction(consoleSummary)} | ${consoleSummary.progress}% | ${consoleSummary.status}`
                            : 'No active run is being processed right now.'}
                    </p>
                </article>
                <article className="agent-strip-card">
                    <span className="agent-strip-label">Next Patrol</span>
                    <strong>{nextPatrolTask ? nextPatrolTask.name : 'Not scheduled'}</strong>
                    <p>{nextPatrolTask ? `Next dispatch ${formatRelative(nextPatrolTask.next_run_at)}` : 'Bootstrap patrols to start 24x7 monitoring.'}</p>
                </article>
            </section>

            <section className="agent-panel agent-ops-filter-panel">
                <div className="agent-panel-header compact">
                    <div>
                        <h2>Operations Filters</h2>
                        <p>Slice the agent workspace by site, camera, and risk level.</p>
                    </div>
                    <button className="btn-ghost" onClick={handleResetOpsFilters}>
                        Reset Filters
                    </button>
                </div>
                <div className="agent-ops-filter-grid">
                    <label className="agent-select-field">
                        <span>Site</span>
                        <select value={siteFilter} onChange={(event) => setSiteFilter(event.target.value)}>
                            <option value="all">All sites</option>
                            {siteOptions.map((option) => (
                                <option key={option} value={option}>{option}</option>
                            ))}
                        </select>
                    </label>
                    <label className="agent-select-field">
                        <span>Camera</span>
                        <select value={cameraFilter} onChange={(event) => setCameraFilter(event.target.value)}>
                            <option value="all">All cameras</option>
                            {cameraOptions.map((option) => (
                                <option key={option} value={option}>{option}</option>
                            ))}
                        </select>
                    </label>
                    <label className="agent-select-field">
                        <span>Risk Level</span>
                        <select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}>
                            <option value="all">All risk levels</option>
                            {riskOptions.map((option) => (
                                <option key={option} value={option}>{option}</option>
                            ))}
                        </select>
                    </label>
                </div>
                <div className="agent-filter-summary">
                    <span>{filteredSessions.length} sessions</span>
                    <span>{filteredActiveRuns.length} active runs</span>
                    <span>{filteredPendingApprovals.length} approvals</span>
                    <span>{filteredScheduledTasks.length} patrol plans</span>
                </div>
            </section>

            <section className="agent-workspace">
                <aside className="agent-panel agent-sessions-panel">
                    <div className="agent-panel-header">
                        <div>
                            <h2>Conversations</h2>
                            <p>Recent sessions from web, email, and patrol workflows.</p>
                        </div>
                        <button className="btn-ghost" onClick={handleNewSession}>New</button>
                    </div>
                    <div className="agent-filter-bar">
                        <label className="agent-search">
                            <Search size={14} />
                            <input
                                type="text"
                                value={sessionQuery}
                                onChange={(event) => setSessionQuery(event.target.value)}
                                placeholder="Search sessions"
                            />
                        </label>
                        <div className="agent-chip-row">
                            {SESSION_SOURCE_FILTERS.map((option) => (
                                <button
                                    key={option.key}
                                    type="button"
                                    className={`agent-chip ${sessionSourceFilter === option.key ? 'is-active' : ''}`}
                                    onClick={() => setSessionSourceFilter(option.key)}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="agent-session-list">
                        {filteredSessions.length ? filteredSessions.map((session) => (
                            <button
                                key={session.id}
                                type="button"
                                className={`agent-session-item ${selectedSessionId === session.id ? 'is-selected' : ''}`}
                                onClick={() => setSelectedSessionId(session.id)}
                            >
                                <div className="agent-session-row">
                                    <strong>{getSessionTitle(session)}</strong>
                                    <span className={`status-chip ${toneClassMap[statusToneMap[session.status] || 'slate']}`}>
                                        {session.status}
                                    </span>
                                </div>
                                <div className="agent-session-meta">
                                    <span>{session.kind}</span>
                                    <span>{session.source}</span>
                                    {session.site_id ? <span>Site {session.site_id}</span> : null}
                                    {session.camera_id ? <span>Camera {session.camera_id}</span> : null}
                                    <span>{formatRelative(session.last_run_at || session.updated_at)}</span>
                                </div>
                            </button>
                        )) : (
                            <div className="agent-empty-state">
                                <Bot size={18} />
                                <span>No sessions match this filter.</span>
                            </div>
                        )}
                    </div>
                </aside>

                <main className="agent-panel agent-chat-panel">
                    <div className="agent-panel-header">
                        <div>
                            <h2>{selectedSession ? getSessionTitle(selectedSession) : 'Start a new conversation'}</h2>
                            <p>
                                {selectedSession
                                    ? `Source: ${selectedSession.source} | Last run ${formatRelative(selectedSession.last_run_at)}`
                                    : 'Send a request and the agent will create a new web session automatically.'}
                            </p>
                        </div>
                        {conversationLoading ? <LoaderCircle size={18} className="spin subtle-icon" /> : null}
                    </div>

                    <div className="agent-message-list" ref={messageListRef}>
                        {messages.length ? messages.map((message) => (
                            <article key={message.id} className={`agent-message ${message.role === 'user' ? 'is-user' : 'is-agent'}`}>
                                <div className="agent-message-role">
                                    {message.role === 'user' ? <MessageSquare size={14} /> : <Bot size={14} />}
                                    <span>{message.role === 'user' ? 'You' : 'Agent'}</span>
                                    <time>{formatDateTime(message.created_at)}</time>
                                </div>
                                <pre className="agent-message-body">{getMessageText(message)}</pre>
                            </article>
                        )) : (
                            <div className="agent-empty-state spacious">
                                <Bot size={22} />
                                <span>Ask the agent to investigate a situation, summarize platform status, or monitor issues.</span>
                            </div>
                        )}
                    </div>

                    <div className="agent-composer">
                        <textarea
                            value={draft}
                            onChange={(event) => setDraft(event.target.value)}
                            placeholder="Describe the task you want the agent to handle..."
                            rows={4}
                        />
                        <div className="agent-composer-footer">
                            <span className="agent-sync-text">Last sync: {lastSyncAt ? formatDateTime(lastSyncAt) : '--'}</span>
                            <button className="btn-primary" onClick={handleSend} disabled={sending || !draft.trim()}>
                                {sending ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}
                                Send to Agent
                            </button>
                        </div>
                    </div>
                </main>

                <aside className="agent-side-column">
                    <section className="agent-panel">
                        <div className="agent-panel-header compact">
                            <div>
                                <h2>What Agent Is Doing</h2>
                                <p>Live runs and approvals.</p>
                            </div>
                        </div>
                        <div className="agent-status-stack">
                            {filteredActiveRuns.length ? filteredActiveRuns.map((run) => (
                                <article
                                    key={run.id}
                                    className={`agent-run-card agent-interactive-card ${recentRunUpdates[run.id] ? 'is-live-update' : ''}`}
                                    onClick={() => openRunDetail(run)}
                                >
                                    <div className="agent-session-row">
                                        <strong>{run.session_title || run.id.slice(0, 8)}</strong>
                                        <span className={`status-chip ${toneClassMap[statusToneMap[run.status] || 'slate']}`}>
                                            {run.status}
                                        </span>
                                    </div>
                                    <p>{run.trigger_text || run.result_summary || 'No prompt text recorded.'}</p>
                                    <div className="agent-progress-track">
                                        <div className="agent-progress-fill" style={{ width: `${run.progress || 0}%` }} />
                                    </div>
                                    <div className="agent-run-meta">
                                        <span>{getRunAction(run)}</span>
                                        {getRunScope(run, sessionMap, taskMap).siteId ? <span>Site {getRunScope(run, sessionMap, taskMap).siteId}</span> : null}
                                        {getRunScope(run, sessionMap, taskMap).cameraId ? <span>Camera {getRunScope(run, sessionMap, taskMap).cameraId}</span> : null}
                                        {getRunRisk(run, taskMap) ? <span>Risk {getRunRisk(run, taskMap)}</span> : null}
                                        <span>{run.progress}%</span>
                                        <span>{formatDuration(run.started_at || run.scheduled_at, run.finished_at)}</span>
                                        <span>{formatRelative(run.last_heartbeat_at || run.started_at || run.scheduled_at)}</span>
                                    </div>
                                </article>
                            )) : (
                                <div className="agent-empty-state">
                                    <Clock3 size={18} />
                                    <span>No active runs at the moment.</span>
                                </div>
                            )}
                        </div>

                        <div className="agent-approval-section">
                            <h3>Pending Approvals</h3>
                            <div className="agent-status-stack">
                                {filteredPendingApprovals.length ? filteredPendingApprovals.map((approval) => (
                                        <article
                                            key={approval.id}
                                            className="agent-approval-card agent-interactive-card"
                                            onClick={() => openApprovalDetail(approval)}
                                        >
                                            <div className="agent-session-row">
                                                <strong>{approval.tool_name}</strong>
                                                <span className="status-chip is-rose">{approval.risk_level}</span>
                                            </div>
                                            <p>{approval.reason || 'Approval requested without a detailed reason.'}</p>
                                            <div className="agent-run-meta">
                                                <span>{approval.session_id.slice(0, 8)}</span>
                                                {getSessionScope(sessionMap.get(approval.session_id)).siteId ? (
                                                    <span>Site {getSessionScope(sessionMap.get(approval.session_id)).siteId}</span>
                                                ) : null}
                                                {getSessionScope(sessionMap.get(approval.session_id)).cameraId ? (
                                                    <span>Camera {getSessionScope(sessionMap.get(approval.session_id)).cameraId}</span>
                                                ) : null}
                                                <span>{formatRelative(approval.created_at)}</span>
                                                <span className={`agent-deadline ${isApprovalUrgent(approval, liveNow) ? 'is-urgent' : ''}`}>
                                                    {formatCountdown(approval.expires_at, liveNow)}
                                                </span>
                                            </div>
                                            <div className="agent-approval-actions">
                                                <button
                                                    className="btn-ghost"
                                                    onClick={(event) => {
                                                        event.stopPropagation();
                                                        handleApprovalDecision(approval.id, 'approved');
                                                    }}
                                                    disabled={approvalSubmittingId === approval.id}
                                                >
                                                    {approvalSubmittingId === approval.id ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />}
                                                    Approve
                                                </button>
                                                <button
                                                    className="btn-ghost danger"
                                                    onClick={(event) => {
                                                        event.stopPropagation();
                                                        handleApprovalDecision(approval.id, 'rejected');
                                                    }}
                                                    disabled={approvalSubmittingId === approval.id}
                                                >
                                                    {approvalSubmittingId === approval.id ? <LoaderCircle size={14} className="spin" /> : <X size={14} />}
                                                    Reject
                                                </button>
                                            </div>
                                        </article>
                                    )) : (
                                    <div className="agent-empty-state">
                                        <ShieldAlert size={18} />
                                        <span>No pending approvals match this filter.</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    </section>

                    <section className="agent-panel">
                        <div className="agent-panel-header compact">
                            <div>
                                <h2>Run History</h2>
                                <p>Recent completions and failures.</p>
                            </div>
                            <div className="agent-chip-row">
                                {RUN_FILTERS.map((option) => (
                                    <button
                                        key={option.key}
                                        type="button"
                                        className={`agent-chip ${runFilter === option.key ? 'is-active' : ''}`}
                                        onClick={() => setRunFilter(option.key)}
                                    >
                                        {option.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div className="agent-run-history">
                            {filteredRunHistory.slice(0, 8).map((run) => (
                                <article
                                    key={run.id}
                                    className={`agent-history-row agent-interactive-card ${recentRunUpdates[run.id] ? 'is-live-update' : ''}`}
                                    onClick={() => openRunDetail(run)}
                                >
                                    <div>
                                        <div className="agent-history-title">{getRunAction(run)}</div>
                                        <div className="agent-history-subtitle">
                                            {run.result_summary || run.last_error || run.trigger_text || 'No summary available.'}
                                        </div>
                                        <div className="agent-inline-meta">
                                            {getRunScope(run, sessionMap, taskMap).siteId ? <span>Site {getRunScope(run, sessionMap, taskMap).siteId}</span> : null}
                                            {getRunScope(run, sessionMap, taskMap).cameraId ? <span>Camera {getRunScope(run, sessionMap, taskMap).cameraId}</span> : null}
                                            {getRunRisk(run, taskMap) ? <span>Risk {getRunRisk(run, taskMap)}</span> : null}
                                        </div>
                                    </div>
                                    <div className="agent-history-meta">
                                        <span className={`status-chip ${toneClassMap[statusToneMap[run.status] || 'slate']}`}>
                                            {run.status}
                                        </span>
                                        <span>{formatDuration(run.started_at || run.scheduled_at, run.finished_at)}</span>
                                        <time>{formatDateTime(run.finished_at || run.started_at || run.scheduled_at)}</time>
                                    </div>
                                </article>
                            ))}
                            {!filteredRunHistory.length ? (
                                <div className="agent-empty-state">
                                    <Activity size={18} />
                                    <span>No runs match this filter.</span>
                                </div>
                            ) : null}
                        </div>
                    </section>

                    <section className="agent-panel">
                        <div className="agent-panel-header compact">
                            <div>
                                <h2>Runtime Alerts</h2>
                                <p>Loop health, automatic recovery, and recent runtime incidents.</p>
                            </div>
                        </div>
                        <div className="agent-run-history">
                            {runtimeAlerts.length ? runtimeAlerts.slice(0, 8).map((alert) => (
                                <article
                                    key={alert.id}
                                    className={`agent-history-row agent-interactive-card ${alert.status === 'open' ? 'is-anomaly' : ''}`}
                                    onClick={() => openAlertDetail(alert)}
                                >
                                    <div>
                                        <div className="agent-history-title">
                                            {alert.status === 'open' ? <span className="agent-alert-dot" /> : null}
                                            {alert.summary}
                                        </div>
                                        <div className="agent-history-subtitle">
                                            {alert.evidence_summary || 'No detailed evidence available.'}
                                        </div>
                                        <div className="agent-inline-meta">
                                            <span>{alert.scope_id || alert.scope_type || 'service-loop'}</span>
                                            <span>{alert.source_rule}</span>
                                        </div>
                                    </div>
                                    <div className="agent-history-meta">
                                        <span className={`status-chip ${toneClassMap[getAlertTone(alert)]}`}>
                                            {alert.status}
                                        </span>
                                        <span className={`status-chip ${toneClassMap[severityToneMap[alert.severity] || 'slate']}`}>
                                            {alert.severity}
                                        </span>
                                        <time>{formatDateTime(alert.updated_at || alert.detected_at)}</time>
                                    </div>
                                </article>
                            )) : (
                                <div className="agent-empty-state">
                                    <ShieldAlert size={18} />
                                    <span>No runtime alerts recorded yet.</span>
                                </div>
                            )}
                        </div>
                    </section>

                    <section className="agent-panel">
                        <div className="agent-panel-header compact">
                            <div>
                                <h2>Patrol Executions</h2>
                                <p>Recent scheduled patrol runs.</p>
                            </div>
                        </div>
                        <div className="agent-run-history">
                            {patrolHistory.length ? patrolHistory.map((run) => (
                                <article
                                    key={run.id}
                                    className={`agent-history-row agent-interactive-card ${run.status === 'failed' ? 'is-anomaly' : ''} ${recentRunUpdates[run.id] ? 'is-live-update' : ''}`}
                                    onClick={() => openRunDetail(run)}
                                >
                                    <div>
                                        <div className="agent-history-title">
                                            {run.status === 'failed' ? <span className="agent-alert-dot" /> : null}
                                            {getRunAction(run)}
                                        </div>
                                        <div className="agent-history-subtitle">
                                            {run.result_summary || run.last_error || 'No patrol summary available.'}
                                        </div>
                                        <div className="agent-inline-meta">
                                            {getRunScope(run, sessionMap, taskMap).siteId ? <span>Site {getRunScope(run, sessionMap, taskMap).siteId}</span> : null}
                                            {getRunScope(run, sessionMap, taskMap).cameraId ? <span>Camera {getRunScope(run, sessionMap, taskMap).cameraId}</span> : null}
                                            {getRunRisk(run, taskMap) ? <span>Risk {getRunRisk(run, taskMap)}</span> : null}
                                        </div>
                                    </div>
                                    <div className="agent-history-meta">
                                        <span className={`status-chip ${toneClassMap[statusToneMap[run.status] || 'slate']}`}>
                                            {run.status}
                                        </span>
                                        <time>{formatDateTime(run.finished_at || run.started_at || run.scheduled_at)}</time>
                                    </div>
                                </article>
                            )) : (
                                <div className="agent-empty-state">
                                    <TimerReset size={18} />
                                    <span>No patrol executions match this filter.</span>
                                </div>
                            )}
                        </div>
                    </section>

                    <section className="agent-panel">
                        <div className="agent-panel-header compact">
                            <div>
                                <h2>Alert Routing</h2>
                                <p>Choose which mailbox receives real-time runtime alerts and recoveries.</p>
                            </div>
                        </div>
                        <div className="agent-subscription-form">
                            <label className="agent-input-field">
                                <span>Alert Email</span>
                                <input
                                    type="email"
                                    value={subscriptionEmail}
                                    onChange={(event) => setSubscriptionEmail(event.target.value)}
                                    placeholder="ops@example.com"
                                />
                            </label>
                            <label className="agent-select-field">
                                <span>Severity Floor</span>
                                <select value={subscriptionSeverity} onChange={(event) => setSubscriptionSeverity(event.target.value)}>
                                    {SUBSCRIPTION_SEVERITY_OPTIONS.map((option) => (
                                        <option key={option.key} value={option.key}>{option.label}</option>
                                    ))}
                                </select>
                            </label>
                            <button
                                className="btn-secondary"
                                onClick={handleCreateSubscription}
                                disabled={subscriptionSubmittingId === 'create' || !subscriptionEmail.trim()}
                            >
                                {subscriptionSubmittingId === 'create' ? <LoaderCircle size={14} className="spin" /> : <Send size={14} />}
                                Add Route
                            </button>
                        </div>
                        <div className="agent-run-history">
                            {subscriptions.length ? subscriptions.map((subscription) => (
                                <article key={subscription.id} className="agent-history-row">
                                    <div>
                                        <div className="agent-history-title">{subscription.target}</div>
                                        <div className="agent-history-subtitle">
                                            {subscription.enabled ? 'Real-time runtime alerts enabled.' : 'Delivery is currently paused.'}
                                        </div>
                                        <div className="agent-inline-meta">
                                            <span>{subscription.channel}</span>
                                            <span>{subscription.schedule_type}</span>
                                            <span>{subscription.severity_floor}+</span>
                                            {subscription.scope_id ? <span>{subscription.scope_id}</span> : <span>global</span>}
                                        </div>
                                    </div>
                                    <div className="agent-inline-actions">
                                        <span className={`status-chip ${subscription.enabled ? 'is-emerald' : 'is-slate'}`}>
                                            {subscription.enabled ? 'enabled' : 'paused'}
                                        </span>
                                        <button
                                            className="btn-ghost"
                                            onClick={() => handleSubscriptionToggle(subscription)}
                                            disabled={subscriptionSubmittingId === `toggle:${subscription.id}`}
                                        >
                                            {subscriptionSubmittingId === `toggle:${subscription.id}` ? (
                                                <LoaderCircle size={14} className="spin" />
                                            ) : subscription.enabled ? (
                                                <PauseCircle size={14} />
                                            ) : (
                                                <PlayCircle size={14} />
                                            )}
                                            {subscription.enabled ? 'Pause' : 'Enable'}
                                        </button>
                                        <button
                                            className="btn-ghost danger"
                                            onClick={() => handleSubscriptionDelete(subscription.id)}
                                            disabled={subscriptionSubmittingId === `delete:${subscription.id}`}
                                        >
                                            {subscriptionSubmittingId === `delete:${subscription.id}` ? <LoaderCircle size={14} className="spin" /> : <X size={14} />}
                                            Remove
                                        </button>
                                    </div>
                                </article>
                            )) : (
                                <div className="agent-empty-state">
                                    <MessageSquare size={18} />
                                    <span>No alert routes configured yet.</span>
                                </div>
                            )}
                        </div>
                    </section>

                    <section className="agent-panel">
                        <div className="agent-panel-header compact">
                            <div>
                                <h2>Patrol Plans</h2>
                                <p>Scheduled patrols and next dispatch time.</p>
                            </div>
                        </div>
                        <div className="agent-run-history">
                            {filteredScheduledTasks.slice(0, 8).map((task) => (
                                <article
                                    key={task.id}
                                    className={`agent-history-row agent-interactive-card ${getTaskAnomaly(task) ? 'is-anomaly' : ''}`}
                                    onClick={() => openTaskDetail(task)}
                                >
                                    <div>
                                        <div className="agent-history-title">
                                            {getTaskAnomaly(task) ? <span className="agent-alert-dot" /> : null}
                                            {task.name}
                                        </div>
                                        <div className="agent-history-subtitle">
                                            {getTaskAnomaly(task) || task.description || task.prompt_template || 'No description available.'}
                                        </div>
                                        <div className="agent-inline-meta">
                                            {getTaskScope(task, sessionMap).siteId ? <span>Site {getTaskScope(task, sessionMap).siteId}</span> : null}
                                            {getTaskScope(task, sessionMap).cameraId ? <span>Camera {getTaskScope(task, sessionMap).cameraId}</span> : null}
                                            <span>{task.cron}</span>
                                            <span>{task.timezone}</span>
                                            <span>{task.risk_profile}</span>
                                        </div>
                                    </div>
                                    <div className="agent-history-meta">
                                        <span className={`status-chip ${task.enabled ? 'is-emerald' : 'is-slate'}`}>
                                            {task.enabled ? 'enabled' : 'disabled'}
                                        </span>
                                        <time>{formatDateTime(task.next_run_at)}</time>
                                        <div className="agent-inline-actions">
                                            <button
                                                className="btn-ghost"
                                                onClick={(event) => {
                                                    event.stopPropagation();
                                                    handleTaskTrigger(task.id);
                                                }}
                                                disabled={taskSubmittingId === `trigger:${task.id}`}
                                            >
                                                {taskSubmittingId === `trigger:${task.id}` ? <LoaderCircle size={14} className="spin" /> : <PlayCircle size={14} />}
                                                Run now
                                            </button>
                                            <button
                                                className="btn-ghost"
                                                onClick={(event) => {
                                                    event.stopPropagation();
                                                    handleTaskToggle(task);
                                                }}
                                                disabled={taskSubmittingId === `toggle:${task.id}`}
                                            >
                                                {taskSubmittingId === `toggle:${task.id}` ? (
                                                    <LoaderCircle size={14} className="spin" />
                                                ) : task.enabled ? (
                                                    <PauseCircle size={14} />
                                                ) : (
                                                    <PlayCircle size={14} />
                                                )}
                                                {task.enabled ? 'Pause' : 'Enable'}
                                            </button>
                                        </div>
                                    </div>
                                </article>
                            ))}
                            {!filteredScheduledTasks.length ? (
                                <div className="agent-empty-state">
                                    <TimerReset size={18} />
                                    <span>No patrol plans match this filter.</span>
                                </div>
                            ) : null}
                        </div>
                    </section>
                </aside>
            </section>

            <section className="agent-panel agent-detail-panel">
                <div className="agent-panel-header">
                    <div>
                        <h2>
                            {selectedDetail?.type === 'run'
                                ? 'Run Detail'
                                : selectedDetail?.type === 'approval'
                                    ? 'Approval Detail'
                                    : selectedDetail?.type === 'alert'
                                        ? 'Runtime Alert Detail'
                                    : selectedDetail?.type === 'task'
                                        ? 'Patrol Task Detail'
                                        : 'Detail Drawer'}
                        </h2>
                        <p>
                            {selectedDetail
                                ? `Inspect the full context for ${selectedDetail.data.id?.slice(0, 8) || 'selected item'}.`
                                : 'Select a run, approval, or patrol plan to inspect its full context.'}
                        </p>
                    </div>
                    {selectedDetail ? (
                        <button className="btn-ghost" onClick={() => setSelectedDetail(null)}>
                            <X size={14} />
                            Close
                        </button>
                    ) : null}
                </div>
                {selectedDetail ? (
                    <div className="agent-detail-content">{detailPanel}</div>
                ) : (
                    <div className="agent-empty-state spacious">
                        <Bot size={22} />
                        <span>Choose a live run, a patrol execution, or an approval request to see full details.</span>
                    </div>
                )}
            </section>

            {toastItems.length ? (
                <div className="agent-toast-stack">
                    {toastItems.map((toast) => (
                        <article key={toast.id} className={`agent-toast is-${toast.tone}`}>
                            <div className="agent-toast-body">
                                <strong>{toast.title}</strong>
                                <p>{toast.body}</p>
                            </div>
                            <button
                                type="button"
                                className="agent-toast-close"
                                onClick={() => dismissToast(toast.id, toast.key)}
                                aria-label="Dismiss notification"
                            >
                                <X size={14} />
                            </button>
                        </article>
                    ))}
                </div>
            ) : null}
        </div>
    );
};

export default AgentOps;
