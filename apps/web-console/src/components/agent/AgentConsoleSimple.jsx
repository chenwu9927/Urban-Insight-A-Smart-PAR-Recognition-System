import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { agentApi } from '../../lib/api';
import {
    ACTIVE_POLL_INTERVAL_MS,
    POLL_INTERVAL_MS,
    formatDateTime,
    getMessageText,
    getSessionTitle,
    sourceToneClass,
    translateAlertStatus,
    translateApprovalStatus,
    translateLoopHealth,
    translateLoopName,
    translateRole,
    translateRunStatus,
    translateSeverity,
    translateSource,
} from './agentUiHelpers';

const STREAM_STEP_MS = 18;
const STREAM_CHARS_PER_TICK = 2;

function AgentConsoleSimple({ user }) {
    const [overview, setOverview] = useState(null);
    const [runtimeStatus, setRuntimeStatus] = useState(null);
    const [unifiedMessages, setUnifiedMessages] = useState([]);
    const [sessions, setSessions] = useState([]);
    const [sessionRuns, setSessionRuns] = useState([]);
    const [approvals, setApprovals] = useState([]);
    const [scheduledTasks, setScheduledTasks] = useState([]);
    const [runtimeAlerts, setRuntimeAlerts] = useState([]);
    const [primarySessionId, setPrimarySessionId] = useState('');
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

    const primarySession = useMemo(
        () =>
            sessions.find((item) => item.id === primarySessionId) ||
            sessions.find((item) => item.source === 'web' && item.kind === 'command') ||
            sessions[0] ||
            null,
        [primarySessionId, sessions],
    );

    const activeSessionRun = useMemo(
        () =>
            sessionRuns.find((item) =>
                ['queued', 'claimed', 'running', 'waiting_approval', 'waiting_input'].includes(item?.status),
            ) || null,
        [sessionRuns],
    );

    const summaryItems = useMemo(
        () => [
            { label: '活跃任务', value: overview?.counts?.active_runs ?? 0 },
            { label: '待审批', value: overview?.counts?.pending_approvals ?? 0 },
            { label: '开放告警', value: runtimeAlerts.length },
        ],
        [overview, runtimeAlerts],
    );

    const loopEntries = Object.entries(runtimeStatus?.loops || {});
    const activeRuns = (overview?.active_runs || []).slice(0, 4);
    const recentApprovals = approvals.slice(0, 3);
    const recentTasks = scheduledTasks.slice(0, 3);
    const openAlerts = runtimeAlerts.slice(0, 3);

    const loadConversation = useCallback(async (sessionId, { background = false } = {}) => {
        if (!background) setConversationLoading(true);
        try {
            const [nextMessages, nextSessions, nextRuns] = await Promise.all([
                agentApi.listUnifiedMessages({ limit: 160 }),
                agentApi.listSessions({ limit: 24, kind: 'command' }),
                sessionId ? agentApi.listRuns({ session_id: sessionId, limit: 20 }) : Promise.resolve([]),
            ]);
            setUnifiedMessages(Array.isArray(nextMessages) ? nextMessages : nextMessages?.items || []);
            setSessions(Array.isArray(nextSessions) ? nextSessions : nextSessions?.items || []);
            setSessionRuns(Array.isArray(nextRuns) ? nextRuns : nextRuns?.items || []);
            const nextPendingRun = (Array.isArray(nextRuns) ? nextRuns : nextRuns?.items || []).find((item) =>
                ['queued', 'claimed', 'running', 'waiting_approval', 'waiting_input'].includes(item?.status),
            );
            setPendingRunId(nextPendingRun?.id || nextPendingRun?.run_id || '');
            setError('');
        } catch (loadError) {
            console.error('Failed to load agent conversation', loadError);
            setError('对话内容加载失败。');
        } finally {
            if (!background) setConversationLoading(false);
        }
    }, []);

    const loadOverview = useCallback(async () => {
        const [nextOverview, nextRuntime, nextApprovals, nextTasks, nextAlerts] = await Promise.all([
            agentApi.overview(),
            agentApi.runtimeStatus(),
            agentApi.listApprovals({ limit: 20 }),
            agentApi.listScheduledTasks({ limit: 20 }),
            agentApi.listAlerts({ status: 'open', limit: 20 }),
        ]);

        setOverview(nextOverview || null);
        setRuntimeStatus(nextRuntime || null);
        setApprovals(Array.isArray(nextApprovals) ? nextApprovals : nextApprovals?.items || []);
        setScheduledTasks(Array.isArray(nextTasks) ? nextTasks : nextTasks?.items || []);
        setRuntimeAlerts(Array.isArray(nextAlerts) ? nextAlerts : nextAlerts?.items || []);
    }, []);

    const refreshAll = useCallback(async () => {
        try {
            await Promise.all([loadOverview(), loadConversation(primarySessionId, { background: true })]);
            setError('');
        } catch (loadError) {
            console.error('Failed to refresh agent console', loadError);
            setError('智能体工作台刷新失败。');
        } finally {
            setLoading(false);
        }
    }, [loadConversation, loadOverview, primarySessionId]);

    useEffect(() => {
        void refreshAll();
        const timer = window.setInterval(() => {
            void refreshAll();
        }, POLL_INTERVAL_MS);
        return () => window.clearInterval(timer);
    }, [refreshAll]);

    useEffect(() => {
        if (!primarySessionId && sessions.length) {
            const nextPrimary = sessions.find((item) => item.source === 'web' && item.kind === 'command')?.id || sessions[0].id;
            setPrimarySessionId(nextPrimary);
        }
    }, [primarySessionId, sessions]);

    useEffect(() => {
        if (!primarySessionId) return;
        void loadConversation(primarySessionId);
    }, [loadConversation, primarySessionId]);

    useEffect(() => {
        const timer = window.setInterval(() => {
            if (primarySessionId) {
                void loadConversation(primarySessionId, { background: true });
            }
        }, activeSessionRun || pendingRunId ? ACTIVE_POLL_INTERVAL_MS : POLL_INTERVAL_MS);
        return () => window.clearInterval(timer);
    }, [activeSessionRun, loadConversation, pendingRunId, primarySessionId]);

    useEffect(() => {
        const latestAssistant = [...unifiedMessages].reverse().find((item) => item.role === 'assistant');
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
    }, [unifiedMessages, startStreamingText, streamState.done, streamState.messageId]);

    useEffect(() => {
        messageListRef.current?.scrollTo({
            top: messageListRef.current.scrollHeight,
            behavior: 'smooth',
        });
    }, [pendingRunId, streamState.text, unifiedMessages]);

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
            let sessionId = primarySessionId;
            if (!sessionId) {
                const newSession = await agentApi.createSession({
                    kind: 'command',
                    title: '统一对话',
                    status: 'active',
                    source: 'web',
                    owner_user_id: user?.id || null,
                });
                sessionId = newSession.id;
                setPrimarySessionId(sessionId);
            }

            const run = await agentApi.createRun({
                session_id: sessionId,
                schedule_mode: 'immediate',
                permission_mode: 'default',
                prompt,
                created_by_user_id: user?.id || null,
            });

            setPendingRunId(run?.id || run?.run_id || '');
            setDraft('');
            await Promise.all([loadOverview(), loadConversation(sessionId, { background: true })]);
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
                setPrimarySessionId(dispatch.session_id);
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

    return (
        <div className="page-shell agent-console-shell">
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
                        <span>当前会话</span>
                        <strong>{primarySession ? getSessionTitle(primarySession) : '未开始'}</strong>
                    </div>
                </div>
            </section>

            <div className="agent-console-grid">
                <section className="card agent-chat-card">
                    <div className="agent-chat-header">
                        <div>
                            <div className="list-row-title">对话</div>
                            <div className="list-row-subtitle">网页和邮件消息会统一显示在这里，时间按东八区展示。</div>
                        </div>
                    </div>

                    <div className="message-list agent-message-list" ref={messageListRef}>
                        {conversationLoading ? <div className="empty-state">正在加载…</div> : null}
                        {!conversationLoading &&
                            unifiedMessages.map((message) => {
                                const fallbackText = getMessageText(message) || '暂无内容';
                                const isStreamingMessage = streamState.messageId === message.id;
                                const text = isStreamingMessage ? streamState.text || fallbackText : fallbackText;
                                return (
                                    <article
                                        key={message.id}
                                        className={`message-bubble ${message.role} ${sourceToneClass(message.session_source)}`}
                                    >
                                        <div className="message-meta-row">
                                            <span className="message-role">{translateRole(message.role)}</span>
                                            <span className="message-source-tag">{translateSource(message.session_source)}</span>
                                            <span className="message-session-title">
                                                {getSessionTitle({
                                                    title: message.session_title,
                                                    source: message.session_source,
                                                    id: message.session_id,
                                                })}
                                            </span>
                                        </div>
                                        <div className="message-text">{text}</div>
                                        <div className="message-time">{formatDateTime(message.created_at)}</div>
                                    </article>
                                );
                            })}
                        {!conversationLoading && pendingRunId ? (
                            <article className="message-bubble assistant is-web">
                                <div className="message-meta-row">
                                    <span className="message-role">智能体</span>
                                    <span className="message-source-tag">网页</span>
                                </div>
                                <div className="message-text">正在思考…</div>
                                <div className="message-time">{translateRunStatus(activeSessionRun?.status || 'running')}</div>
                            </article>
                        ) : null}
                        {!conversationLoading && !unifiedMessages.length && !pendingRunId ? (
                            <div className="empty-state">还没有对话。你可以直接开始提问，也可以先给智能体发邮件。</div>
                        ) : null}
                    </div>

                    <div className="composer agent-composer">
                        <textarea
                            value={draft}
                            onChange={(event) => setDraft(event.target.value)}
                            placeholder="例如：总结当前异常、检查系统状态、解释一段视频。"
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
                </section>

                <aside className="agent-side-rail">
                    <section className="card compact-card">
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
                    </section>

                    <section className="card compact-card">
                        <div className="list-row-title">当前任务</div>
                        <div className="list compact-list" style={{ marginTop: 10 }}>
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
                    </section>

                    <section className="card compact-card">
                        <div className="list-row-title">待审批</div>
                        <div className="list compact-list" style={{ marginTop: 10 }}>
                            {recentApprovals.map((approval) => (
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
                            {!recentApprovals.length ? <div className="empty-state">暂无待审批。</div> : null}
                        </div>
                    </section>

                    <section className="card compact-card">
                        <div className="list-row-title">巡检计划</div>
                        {!scheduledTasks.length ? (
                            <div className="action-row" style={{ marginTop: 10 }}>
                                <button type="button" className="btn-primary" onClick={handleBootstrapDefaults} disabled={bootstrapping}>
                                    {bootstrapping ? '初始化中…' : '初始化默认巡检'}
                                </button>
                            </div>
                        ) : null}
                        <div className="list compact-list" style={{ marginTop: 10 }}>
                            {recentTasks.map((task) => (
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
                            {!recentTasks.length ? <div className="empty-state">暂无巡检计划。</div> : null}
                        </div>
                    </section>

                    {openAlerts.length ? (
                        <section className="card compact-card">
                            <div className="list-row-title">开放告警</div>
                            <div className="list compact-list" style={{ marginTop: 10 }}>
                                {openAlerts.map((alert) => (
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
                        </section>
                    ) : null}
                </aside>
            </div>
        </div>
    );
}

export default AgentConsoleSimple;
