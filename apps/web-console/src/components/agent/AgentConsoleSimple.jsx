import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { agentApi } from '../../lib/api';
import { toTimestamp } from '../../lib/time';
import {
    ACTIVE_POLL_INTERVAL_MS,
    POLL_INTERVAL_MS,
    formatDateTime,
    getMessageText,
    getSessionTitle,
    getSummaryText,
    isPlaceholderTitle,
    isRunActive,
    sortSessions,
    translateAlertStatus,
    translateApprovalStatus,
    translateLoopHealth,
    translateLoopName,
    translateRunStatus,
    translateScheduleMode,
    translateSeverity,
    translateSource,
} from './agentUiHelpers';

const STREAM_STEP_MS = 18;
const STREAM_CHARS_PER_TICK = 2;
const PLACEHOLDER_SESSION_MAX_AGE_MS = 24 * 60 * 60 * 1000;

function shouldHideSession(item, selectedSessionId) {
    if (!item) return true;
    if (item.id === selectedSessionId) return false;
    if (item.source !== 'web' || item.kind !== 'command') return true;
    if (!isPlaceholderTitle(item.title)) return false;
    const ageMs = Date.now() - toTimestamp(item.last_run_at || item.updated_at || 0);
    return ageMs > PLACEHOLDER_SESSION_MAX_AGE_MS;
}

function AgentConsoleSimple({ user }) {
    const [overview, setOverview] = useState(null);
    const [runtimeStatus, setRuntimeStatus] = useState(null);
    const [sessions, setSessions] = useState([]);
    const [approvals, setApprovals] = useState([]);
    const [scheduledTasks, setScheduledTasks] = useState([]);
    const [runtimeAlerts, setRuntimeAlerts] = useState([]);
    const [selectedSessionId, setSelectedSessionId] = useState('');
    const [messages, setMessages] = useState([]);
    const [sessionRuns, setSessionRuns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [conversationLoading, setConversationLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [approvalSubmittingId, setApprovalSubmittingId] = useState('');
    const [taskSubmittingId, setTaskSubmittingId] = useState('');
    const [bootstrapping, setBootstrapping] = useState(false);
    const [draft, setDraft] = useState('');
    const [error, setError] = useState('');
    const [pendingRunId, setPendingRunId] = useState('');
    const [streamState, setStreamState] = useState({ messageId: '', text: '', done: true });
    const messageListRef = useRef(null);
    const streamTimerRef = useRef(null);
    const animatedMessageIdsRef = useRef(new Set());

    const selectedSession = useMemo(
        () => sessions.find((item) => item.id === selectedSessionId) || null,
        [sessions, selectedSessionId],
    );

    const visibleSessions = useMemo(
        () => sessions.filter((item) => !shouldHideSession(item, selectedSessionId)),
        [selectedSessionId, sessions],
    );

    const activeSessionRun = useMemo(
        () => sessionRuns.find((item) => isRunActive(item)) || null,
        [sessionRuns],
    );

    const selectedSummary = useMemo(
        () => getSummaryText(selectedSession?.state_patch?.context_summary),
        [selectedSession],
    );

    const clearStreamTimer = useCallback(() => {
        if (streamTimerRef.current) {
            window.clearInterval(streamTimerRef.current);
            streamTimerRef.current = null;
        }
    }, []);

    const startStreamingText = useCallback(
        (messageId, fullText) => {
            if (!messageId || !fullText) return;
            clearStreamTimer();
            let cursor = 0;
            setStreamState({ messageId, text: '', done: false });
            streamTimerRef.current = window.setInterval(() => {
                cursor = Math.min(fullText.length, cursor + STREAM_CHARS_PER_TICK);
                const nextText = fullText.slice(0, cursor);
                const done = cursor >= fullText.length;
                setStreamState({ messageId, text: nextText, done });
                if (done) {
                    clearStreamTimer();
                    animatedMessageIdsRef.current.add(messageId);
                }
            }, STREAM_STEP_MS);
        },
        [clearStreamTimer],
    );

    const loadOverview = useCallback(async () => {
        const [nextOverview, nextRuntime, nextSessions, nextApprovals, nextTasks, nextAlerts] = await Promise.all([
            agentApi.overview(),
            agentApi.runtimeStatus(),
            agentApi.listSessions({ limit: 40, kind: 'command', source: 'web' }),
            agentApi.listApprovals({ limit: 20 }),
            agentApi.listScheduledTasks({ limit: 20 }),
            agentApi.listAlerts({ limit: 20 }),
        ]);

        const orderedSessions = sortSessions(nextSessions || []);
        const filteredSessions = orderedSessions.filter((item) => !shouldHideSession(item, ''));
        setOverview(nextOverview || null);
        setRuntimeStatus(nextRuntime || null);
        setSessions(orderedSessions);
        setApprovals(nextApprovals || []);
        setScheduledTasks(nextTasks || []);
        setRuntimeAlerts(nextAlerts || []);
        setSelectedSessionId((current) => {
            if (current && orderedSessions.some((item) => item.id === current)) {
                return current;
            }
            return filteredSessions[0]?.id || '';
        });
    }, []);

    const loadConversation = useCallback(async (sessionId, { background = false } = {}) => {
        if (!sessionId) {
            setMessages([]);
            setSessionRuns([]);
            setPendingRunId('');
            return;
        }
        if (!background) setConversationLoading(true);
        try {
            const [nextMessages, nextRuns] = await Promise.all([
                agentApi.listSessionMessages(sessionId, { limit: 80 }),
                agentApi.listRuns({ session_id: sessionId, limit: 20 }),
            ]);
            setMessages(nextMessages || []);
            setSessionRuns(nextRuns || []);
            const nextPendingRun = (nextRuns || []).find((item) => isRunActive(item));
            setPendingRunId(nextPendingRun?.id || '');
        } catch (loadError) {
            console.error('Failed to load conversation', loadError);
            if (loadError?.response?.status === 404) {
                setSelectedSessionId('');
                setMessages([]);
                setSessionRuns([]);
                setPendingRunId('');
                return;
            }
            setError('会话内容加载失败。');
        } finally {
            if (!background) setConversationLoading(false);
        }
    }, []);

    const refreshAll = useCallback(async () => {
        try {
            await loadOverview();
            setError('');
        } catch (loadError) {
            console.error('Failed to load agent console', loadError);
            setError('智能体工作台刷新失败。');
        } finally {
            setLoading(false);
        }
    }, [loadOverview]);

    useEffect(() => {
        void refreshAll();
        const timer = window.setInterval(() => {
            void refreshAll();
        }, POLL_INTERVAL_MS);
        return () => window.clearInterval(timer);
    }, [refreshAll]);

    useEffect(() => {
        void loadConversation(selectedSessionId);
    }, [loadConversation, selectedSessionId]);

    useEffect(() => {
        if (!selectedSessionId) return undefined;
        const timer = window.setInterval(() => {
            void loadConversation(selectedSessionId, { background: true });
        }, activeSessionRun || pendingRunId ? ACTIVE_POLL_INTERVAL_MS : POLL_INTERVAL_MS);
        return () => window.clearInterval(timer);
    }, [activeSessionRun, loadConversation, pendingRunId, selectedSessionId]);

    useEffect(() => {
        const latestAssistant = [...messages].reverse().find((item) => item.role === 'assistant');
        if (!latestAssistant) return;
        const fullText = getMessageText(latestAssistant);
        if (!fullText) return;
        if (animatedMessageIdsRef.current.has(latestAssistant.id)) {
            if (streamState.messageId !== latestAssistant.id || !streamState.done) {
                setStreamState({ messageId: latestAssistant.id, text: fullText, done: true });
            }
            return;
        }
        startStreamingText(latestAssistant.id, fullText);
    }, [messages, startStreamingText, streamState.done, streamState.messageId]);

    useEffect(() => {
        messageListRef.current?.scrollTo({
            top: messageListRef.current.scrollHeight,
            behavior: 'smooth',
        });
    }, [messages, pendingRunId, streamState.text]);

    useEffect(
        () => () => {
            clearStreamTimer();
        },
        [clearStreamTimer],
    );

    const handleSend = async () => {
        const prompt = draft.trim();
        if (!prompt || sending) return;
        setSending(true);
        setError('');
        try {
            let sessionId = selectedSessionId;
            if (!sessionId) {
                const newSession = await agentApi.createSession({
                    kind: 'command',
                    title: prompt.slice(0, 48),
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
                created_by_user_id: user?.id || null,
            });

            setPendingRunId(run?.id || '');
            setDraft('');
            await Promise.all([refreshAll(), loadConversation(sessionId, { background: true })]);
        } catch (sendError) {
            console.error('Failed to send agent request', sendError);
            setError(sendError?.response?.data?.detail || '发送失败。');
        } finally {
            setSending(false);
        }
    };

    const handleApproval = async (approvalId, status) => {
        setApprovalSubmittingId(approvalId);
        try {
            await agentApi.answerApproval(approvalId, {
                status,
                answered_by_user_id: user?.id || null,
                answers: { source: 'web', decided_at: new Date().toISOString() },
            });
            await refreshAll();
        } catch (answerError) {
            console.error('Failed to answer approval', answerError);
            setError('审批处理失败。');
        } finally {
            setApprovalSubmittingId('');
        }
    };

    const handleTaskTrigger = async (taskId) => {
        setTaskSubmittingId(`trigger:${taskId}`);
        try {
            const dispatch = await agentApi.triggerScheduledTask(taskId);
            if (dispatch?.session_id) {
                setSelectedSessionId(dispatch.session_id);
                await loadConversation(dispatch.session_id, { background: true });
            }
            await refreshAll();
        } catch (triggerError) {
            console.error('Failed to trigger task', triggerError);
            setError('手动执行巡检失败。');
        } finally {
            setTaskSubmittingId('');
        }
    };

    const handleTaskToggle = async (task) => {
        setTaskSubmittingId(`toggle:${task.id}`);
        try {
            await agentApi.updateScheduledTask(task.id, { enabled: !task.enabled });
            await refreshAll();
        } catch (updateError) {
            console.error('Failed to update task', updateError);
            setError('巡检计划更新失败。');
        } finally {
            setTaskSubmittingId('');
        }
    };

    const handleBootstrapDefaults = async () => {
        setBootstrapping(true);
        try {
            await agentApi.bootstrapDefaults();
            await refreshAll();
        } catch (bootstrapError) {
            console.error('Failed to bootstrap patrols', bootstrapError);
            setError('初始化默认巡检失败。');
        } finally {
            setBootstrapping(false);
        }
    };

    const summaryItems = [
        { label: '活跃任务', value: overview?.counts?.active_runs ?? 0 },
        { label: '待审批', value: overview?.counts?.pending_approvals ?? 0 },
        { label: '启用巡检', value: overview?.counts?.enabled_scheduled_tasks ?? 0 },
    ];

    const activeRuns = (overview?.active_runs || []).slice(0, 4);
    const loopEntries = Object.entries(runtimeStatus?.loops || {});
    const recentAlerts = runtimeAlerts.slice(0, 4);

    return (
        <div className="page-shell">
            {error ? <div className="notice error">{error}</div> : null}
            {loading ? <div className="empty-state">正在加载…</div> : null}

            <section className="card subtle-card compact-card">
                <div className="compact-summary">
                    {summaryItems.map((item) => (
                        <div key={item.label} className="compact-metric">
                            <span>{item.label}</span>
                            <strong>{item.value}</strong>
                        </div>
                    ))}
                    <div className="compact-metric is-muted">
                        <span>开放告警</span>
                        <strong>{runtimeAlerts.filter((item) => item.status === 'open').length}</strong>
                    </div>
                </div>
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="list-row-title">会话</div>
                    <div className="list compact-list" style={{ marginTop: 10 }}>
                        {visibleSessions.slice(0, 8).map((session) => (
                            <button
                                key={session.id}
                                type="button"
                                className={`list-row as-button ${selectedSessionId === session.id ? 'selected' : ''}`}
                                onClick={() => setSelectedSessionId(session.id)}
                            >
                                <div className="list-row-main">
                                    <div className="list-row-title">{getSessionTitle(session)}</div>
                                    <div className="list-row-subtitle">
                                        {translateSource(session.source)} · {formatDateTime(session.updated_at)}
                                    </div>
                                </div>
                            </button>
                        ))}
                        {!visibleSessions.length ? <div className="empty-state">暂无会话。</div> : null}
                    </div>
                    {selectedSession ? (
                        <div className="subsection compact-subsection">
                            <h3>当前摘要</h3>
                            <pre className="summary-box">{selectedSummary}</pre>
                        </div>
                    ) : null}
                </section>

                <section className="card">
                    <div className="list-row-title">系统状态</div>
                    <div className="list compact-list" style={{ marginTop: 10 }}>
                        {loopEntries.map(([name, loop]) => (
                            <div key={name} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{translateLoopName(name)}</div>
                                    <div className="list-row-subtitle">最近心跳 {formatDateTime(loop.last_seen_at)}</div>
                                </div>
                                <div className="list-row-meta">
                                    <span className={`status-tag ${loop.health === 'healthy' ? 'is-success' : 'is-warning'}`}>
                                        {translateLoopHealth(loop.health)}
                                    </span>
                                </div>
                            </div>
                        ))}
                        {!loopEntries.length ? <div className="empty-state">暂无状态。</div> : null}
                    </div>

                    <div className="subsection compact-subsection">
                        <h3>当前任务</h3>
                        <div className="list compact-list">
                            {activeRuns.map((run) => (
                                <div key={run.id} className="list-row">
                                    <div className="list-row-main">
                                        <div className="list-row-title">{run.session_title || '未命名任务'}</div>
                                        <div className="list-row-subtitle">{run.result_summary || run.trigger_text || '处理中'}</div>
                                    </div>
                                    <div className="list-row-meta">
                                        <span>{translateRunStatus(run.status)}</span>
                                    </div>
                                </div>
                            ))}
                            {!activeRuns.length ? <div className="empty-state">暂无活跃任务。</div> : null}
                        </div>
                    </div>

                    {recentAlerts.length ? (
                        <div className="subsection compact-subsection">
                            <h3>最近告警</h3>
                            <div className="list compact-list">
                                {recentAlerts.map((alert) => (
                                    <div key={alert.id} className="list-row">
                                        <div className="list-row-main">
                                            <div className="list-row-title">{alert.summary || '运行告警'}</div>
                                            <div className="list-row-subtitle">{formatDateTime(alert.created_at)}</div>
                                        </div>
                                        <div className="list-row-meta">
                                            <span className="status-tag is-warning">{translateSeverity(alert.severity)}</span>
                                            <span>{translateAlertStatus(alert.status)}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : null}
                </section>
            </div>

            <section className="card">
                <div className="list-row-title">对话</div>

                <div className="message-list" ref={messageListRef} style={{ marginTop: 10 }}>
                    {conversationLoading ? <div className="empty-state">正在加载…</div> : null}
                    {!conversationLoading &&
                        messages.map((message) => {
                            const fallbackText = getMessageText(message) || '暂无内容';
                            const isStreamingMessage = streamState.messageId === message.id;
                            const text = isStreamingMessage ? streamState.text || fallbackText : fallbackText;
                            return (
                                <article key={message.id} className={`message-bubble ${message.role}`}>
                                    <div className="message-role">{message.role === 'user' ? '你' : '智能体'}</div>
                                    <div className="message-text">{text}</div>
                                    <div className="message-time">{formatDateTime(message.created_at)}</div>
                                </article>
                            );
                        })}
                    {!conversationLoading && pendingRunId ? (
                        <article className="message-bubble assistant">
                            <div className="message-role">智能体</div>
                            <div className="message-text">正在思考…</div>
                            <div className="message-time">{translateRunStatus(activeSessionRun?.status || 'running')}</div>
                        </article>
                    ) : null}
                    {!conversationLoading && !messages.length && !pendingRunId ? <div className="empty-state">暂无消息。</div> : null}
                </div>

                <div className="composer">
                    <textarea
                        value={draft}
                        onChange={(event) => setDraft(event.target.value)}
                        placeholder="例如：总结当前异常、解释某段视频、检查系统状态。"
                        onKeyDown={(event) => {
                            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                                event.preventDefault();
                                void handleSend();
                            }
                        }}
                    />
                    <div className="action-row">
                        <span className="composer-tip">Ctrl / Cmd + Enter 发送</span>
                        <button type="button" className="btn-primary" onClick={handleSend} disabled={sending || !draft.trim()}>
                            {sending ? '发送中…' : '发送'}
                        </button>
                    </div>
                </div>

                {sessionRuns.length ? (
                    <div className="subsection compact-subsection">
                        <h3>运行记录</h3>
                        <div className="list compact-list">
                            {sessionRuns.slice(0, 6).map((run) => (
                                <div key={run.id} className="list-row">
                                    <div className="list-row-main">
                                        <div className="list-row-title">{run.result_summary || '任务运行'}</div>
                                        <div className="list-row-subtitle">
                                            {translateScheduleMode(run.schedule_mode)} · {formatDateTime(run.started_at || run.scheduled_at)}
                                        </div>
                                    </div>
                                    <div className="list-row-meta">
                                        <span>{translateRunStatus(run.status)}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                ) : null}
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="list-row-title">待审批</div>
                    <div className="list compact-list" style={{ marginTop: 10 }}>
                        {approvals.map((approval) => (
                            <div key={approval.id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{approval.summary || approval.reason || '审批请求'}</div>
                                    <div className="list-row-subtitle">
                                        风险 {approval.risk_level || '--'} · 截止 {formatDateTime(approval.expires_at)}
                                    </div>
                                </div>
                                <div className="list-row-meta">
                                    <span>{translateApprovalStatus(approval.status)}</span>
                                    {approval.status === 'pending' ? (
                                        <div className="table-actions">
                                            <button
                                                type="button"
                                                className="btn-ghost"
                                                onClick={() => handleApproval(approval.id, 'approved')}
                                                disabled={approvalSubmittingId === approval.id}
                                            >
                                                批准
                                            </button>
                                            <button
                                                type="button"
                                                className="btn-ghost danger"
                                                onClick={() => handleApproval(approval.id, 'rejected')}
                                                disabled={approvalSubmittingId === approval.id}
                                            >
                                                拒绝
                                            </button>
                                        </div>
                                    ) : null}
                                </div>
                            </div>
                        ))}
                        {!approvals.length ? <div className="empty-state">暂无待审批。</div> : null}
                    </div>
                </section>

                <section className="card">
                    <div className="list-row-title">巡检计划</div>
                    {!scheduledTasks.length ? (
                        <div className="action-row" style={{ marginTop: 10 }}>
                            <button type="button" className="btn-primary" onClick={handleBootstrapDefaults} disabled={bootstrapping}>
                                {bootstrapping ? '初始化中…' : '初始化默认巡检'}
                            </button>
                        </div>
                    ) : null}
                    <div className="list compact-list" style={{ marginTop: 10 }}>
                        {scheduledTasks.map((task) => (
                            <div key={task.id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{task.name}</div>
                                    <div className="list-row-subtitle">下次运行 {formatDateTime(task.next_run_at)}</div>
                                </div>
                                <div className="list-row-meta">
                                    <button
                                        type="button"
                                        className="btn-ghost"
                                        onClick={() => handleTaskTrigger(task.id)}
                                        disabled={taskSubmittingId === `trigger:${task.id}`}
                                    >
                                        运行
                                    </button>
                                    <button
                                        type="button"
                                        className="btn-ghost"
                                        onClick={() => handleTaskToggle(task)}
                                        disabled={taskSubmittingId === `toggle:${task.id}`}
                                    >
                                        {task.enabled ? '暂停' : '启用'}
                                    </button>
                                </div>
                            </div>
                        ))}
                        {!scheduledTasks.length ? <div className="empty-state">暂无巡检计划。</div> : null}
                    </div>
                </section>
            </div>
        </div>
    );
}

export default AgentConsoleSimple;
