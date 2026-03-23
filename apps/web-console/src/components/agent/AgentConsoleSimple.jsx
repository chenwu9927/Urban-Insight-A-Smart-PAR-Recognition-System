import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { agentApi } from '../../lib/api';
import {
    POLL_INTERVAL_MS,
    SUBSCRIPTION_SEVERITY_OPTIONS,
    formatDateTime,
    getMessageText,
    getSessionTitle,
    getSummaryText,
    sortSessions,
    translateAlertStatus,
    translateApprovalStatus,
    translateChannel,
    translateLoopHealth,
    translateLoopName,
    translateRunStatus,
    translateScheduleMode,
    translateScheduleType,
    translateSeverity,
    translateSource,
} from './agentUiHelpers';

function AgentConsoleSimple({ user }) {
    const [overview, setOverview] = useState(null);
    const [runtimeStatus, setRuntimeStatus] = useState(null);
    const [sessions, setSessions] = useState([]);
    const [scheduledTasks, setScheduledTasks] = useState([]);
    const [approvals, setApprovals] = useState([]);
    const [runtimeAlerts, setRuntimeAlerts] = useState([]);
    const [subscriptions, setSubscriptions] = useState([]);
    const [selectedSessionId, setSelectedSessionId] = useState('');
    const [messages, setMessages] = useState([]);
    const [sessionRuns, setSessionRuns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [conversationLoading, setConversationLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [taskSubmittingId, setTaskSubmittingId] = useState('');
    const [approvalSubmittingId, setApprovalSubmittingId] = useState('');
    const [subscriptionSubmittingId, setSubscriptionSubmittingId] = useState('');
    const [bootstrapping, setBootstrapping] = useState(false);
    const [draft, setDraft] = useState('');
    const [subscriptionEmail, setSubscriptionEmail] = useState('');
    const [subscriptionSeverity, setSubscriptionSeverity] = useState('warning');
    const [error, setError] = useState('');
    const [lastSyncAt, setLastSyncAt] = useState('');
    const messageListRef = useRef(null);

    const selectedSession = useMemo(
        () => sessions.find((item) => item.id === selectedSessionId) || null,
        [sessions, selectedSessionId],
    );

    const loadOverview = useCallback(async () => {
        const [nextOverview, nextRuntime, nextSessions, nextApprovals, nextTasks, nextAlerts, nextSubscriptions] =
            await Promise.all([
                agentApi.overview(),
                agentApi.runtimeStatus(),
                agentApi.listSessions({ limit: 40 }),
                agentApi.listApprovals({ limit: 20 }),
                agentApi.listScheduledTasks({ limit: 20 }),
                agentApi.listAlerts({ limit: 20 }),
                agentApi.listSubscriptions({ limit: 20 }),
            ]);

        const orderedSessions = sortSessions(nextSessions || []);

        setOverview(nextOverview);
        setRuntimeStatus(nextRuntime);
        setSessions(orderedSessions);
        setApprovals(nextApprovals || []);
        setScheduledTasks(nextTasks || []);
        setRuntimeAlerts(nextAlerts || []);
        setSubscriptions(nextSubscriptions || []);
        setLastSyncAt(new Date().toISOString());

        setSelectedSessionId((current) => {
            if (current && orderedSessions.some((item) => item.id === current)) {
                return current;
            }
            return orderedSessions[0]?.id || '';
        });
    }, []);

    const loadConversation = useCallback(async (sessionId) => {
        if (!sessionId) {
            setMessages([]);
            setSessionRuns([]);
            return;
        }

        setConversationLoading(true);
        try {
            const [nextMessages, nextRuns] = await Promise.all([
                agentApi.listSessionMessages(sessionId, { limit: 80 }),
                agentApi.listRuns({ session_id: sessionId, limit: 30 }),
            ]);
            setMessages(nextMessages || []);
            setSessionRuns(nextRuns || []);
        } catch (loadError) {
            console.error('Failed to load conversation', loadError);
            setError('会话内容加载失败。');
        } finally {
            setConversationLoading(false);
        }
    }, []);

    const refreshAll = useCallback(async () => {
        try {
            await loadOverview();
            setError('');
        } catch (loadError) {
            console.error('Failed to load agent console', loadError);
            setError('智能体面板刷新失败。');
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
        messageListRef.current?.scrollTo({
            top: messageListRef.current.scrollHeight,
            behavior: 'smooth',
        });
    }, [messages]);

    const handleSend = async () => {
        const prompt = draft.trim();
        if (!prompt || sending) {
            return;
        }

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

            await agentApi.createRun({
                session_id: sessionId,
                schedule_mode: 'immediate',
                permission_mode: 'default',
                prompt,
                created_by_user_id: user?.id || null,
            });

            setDraft('');
            await Promise.all([refreshAll(), loadConversation(sessionId)]);
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
            }
            await Promise.all([refreshAll(), loadConversation(dispatch?.session_id || selectedSessionId)]);
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

    const handleCreateSubscription = async () => {
        const target = subscriptionEmail.trim().toLowerCase();
        if (!target || subscriptionSubmittingId) {
            return;
        }

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
            await refreshAll();
        } catch (createError) {
            console.error('Failed to create subscription', createError);
            setError('新增告警订阅失败。');
        } finally {
            setSubscriptionSubmittingId('');
        }
    };

    const handleSubscriptionToggle = async (subscription) => {
        setSubscriptionSubmittingId(`toggle:${subscription.id}`);
        try {
            await agentApi.updateSubscription(subscription.id, { enabled: !subscription.enabled });
            await refreshAll();
        } catch (toggleError) {
            console.error('Failed to update subscription', toggleError);
            setError('更新告警订阅失败。');
        } finally {
            setSubscriptionSubmittingId('');
        }
    };

    const handleSubscriptionDelete = async (subscriptionId) => {
        setSubscriptionSubmittingId(`delete:${subscriptionId}`);
        try {
            await agentApi.deleteSubscription(subscriptionId);
            await refreshAll();
        } catch (deleteError) {
            console.error('Failed to delete subscription', deleteError);
            setError('删除告警订阅失败。');
        } finally {
            setSubscriptionSubmittingId('');
        }
    };

    return (
        <div className="page-shell">
            <section className="page-header">
                <div className="page-title-group">
                    <span>智能体</span>
                    <h1>智能体工作台</h1>
                    <p>通过网页和智能体对话，同时查看运行状态、历史消息、审批、巡检和告警。</p>
                </div>
                <div className="page-header-actions">
                    <span className="page-chip">最近同步：{formatDateTime(lastSyncAt)}</span>
                    <button type="button" className="btn-secondary" onClick={() => void refreshAll()}>
                        刷新
                    </button>
                </div>
            </section>

            {error ? <div className="notice error">{error}</div> : null}

            <section className="stat-grid">
                <div className="stat-card">
                    <span className="stat-label">活跃运行</span>
                    <strong className="stat-value">{overview?.counts?.active_runs ?? 0}</strong>
                    <p className="stat-hint">当前正在执行的任务数。</p>
                </div>
                <div className="stat-card">
                    <span className="stat-label">排队任务</span>
                    <strong className="stat-value">{overview?.counts?.queued_runs ?? 0}</strong>
                    <p className="stat-hint">等待调度的任务数。</p>
                </div>
                <div className="stat-card">
                    <span className="stat-label">待审批</span>
                    <strong className="stat-value">{overview?.counts?.pending_approvals ?? 0}</strong>
                    <p className="stat-hint">需要人工确认的请求。</p>
                </div>
                <div className="stat-card">
                    <span className="stat-label">巡检计划</span>
                    <strong className="stat-value">{overview?.counts?.enabled_scheduled_tasks ?? 0}</strong>
                    <p className="stat-hint">当前启用的巡检任务。</p>
                </div>
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">运行状态</h2>
                            <p className="card-subtitle">查看后台循环和当前活跃任务。</p>
                        </div>
                    </div>
                    <div className="list">
                        {Object.entries(runtimeStatus?.loops || {}).map(([name, loop]) => (
                            <div key={name} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{translateLoopName(name)}</div>
                                    <div className="list-row-subtitle">最近心跳 {formatDateTime(loop.last_seen_at)}</div>
                                </div>
                                <div className="list-row-meta">
                                    <span className="status-tag is-info">{translateLoopHealth(loop.health)}</span>
                                    <span>重启 {loop.restart_count ?? 0} 次</span>
                                </div>
                            </div>
                        ))}
                        {!Object.keys(runtimeStatus?.loops || {}).length ? <div className="empty-state">暂无运行状态。</div> : null}
                    </div>
                    <div className="subsection">
                        <h3>当前活跃任务</h3>
                        <div className="list">
                            {(overview?.active_runs || []).map((run) => (
                                <div key={run.id} className="list-row">
                                    <div className="list-row-main">
                                        <div className="list-row-title">{run.session_title || '未命名任务'}</div>
                                        <div className="list-row-subtitle">{run.result_summary || run.trigger_text || '正在处理中'}</div>
                                    </div>
                                    <div className="list-row-meta">
                                        <span className="status-tag is-warning">{translateRunStatus(run.status)}</span>
                                        <span>{run.progress ?? 0}%</span>
                                    </div>
                                </div>
                            ))}
                            {!(overview?.active_runs || []).length ? <div className="empty-state">当前没有活跃任务。</div> : null}
                        </div>
                    </div>
                </section>

                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">会话概览</h2>
                            <p className="card-subtitle">查看近期会话和摘要。</p>
                        </div>
                    </div>
                    <div className="list">
                        {sessions.slice(0, 6).map((session) => (
                            <button
                                key={session.id}
                                type="button"
                                className={`list-row as-button ${selectedSessionId === session.id ? 'selected' : ''}`}
                                onClick={() => setSelectedSessionId(session.id)}
                            >
                                <div className="list-row-main">
                                    <div className="list-row-title">{getSessionTitle(session)}</div>
                                    <div className="list-row-subtitle">{translateSource(session.source)} / {formatDateTime(session.updated_at)}</div>
                                </div>
                            </button>
                        ))}
                        {!sessions.length ? <div className="empty-state">暂无会话。</div> : null}
                    </div>
                    {selectedSession ? (
                        <div className="subsection">
                            <h3>当前会话摘要</h3>
                            <pre className="summary-box">{getSummaryText(selectedSession.state_patch?.context_summary)}</pre>
                        </div>
                    ) : null}
                </section>
            </div>

            <section className="card">
                <div className="card-header">
                    <div>
                        <h2 className="card-title">与智能体对话</h2>
                        <p className="card-subtitle">查看历史会话，直接发消息，并查看该会话的运行记录。</p>
                    </div>
                </div>
                <div className="conversation-layout">
                    <aside className="conversation-sidebar">
                        <div className="list">
                            {sessions.map((session) => (
                                <button
                                    key={session.id}
                                    type="button"
                                    className={`list-row as-button ${selectedSessionId === session.id ? 'selected' : ''}`}
                                    onClick={() => setSelectedSessionId(session.id)}
                                >
                                    <div className="list-row-main">
                                        <div className="list-row-title">{getSessionTitle(session)}</div>
                                        <div className="list-row-subtitle">{translateSource(session.source)} / {formatDateTime(session.updated_at)}</div>
                                    </div>
                                </button>
                            ))}
                            {!sessions.length ? <div className="empty-state">还没有任何会话。</div> : null}
                        </div>
                    </aside>

                    <div className="conversation-main">
                        <div ref={messageListRef} className="message-list">
                            {conversationLoading ? <div className="empty-state">正在加载会话内容...</div> : null}
                            {!conversationLoading && messages.map((message) => (
                                <article key={message.id} className={`message-bubble ${message.role}`}>
                                    <div className="message-role">
                                        {message.role === 'user' ? '你' : message.role === 'assistant' ? '智能体' : '系统'}
                                    </div>
                                    <div className="message-text">{getMessageText(message) || '暂无内容'}</div>
                                    <div className="message-time">{formatDateTime(message.created_at)}</div>
                                </article>
                            ))}
                            {!conversationLoading && !messages.length ? <div className="empty-state">当前会话还没有消息。</div> : null}
                        </div>

                        <div className="composer">
                            <textarea
                                value={draft}
                                onChange={(event) => setDraft(event.target.value)}
                                placeholder="输入任务，例如：检查当前系统状态并总结异常。"
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                                        event.preventDefault();
                                        void handleSend();
                                    }
                                }}
                            />
                            <div className="action-row">
                                <span className="composer-tip">按 Ctrl/Cmd + Enter 发送</span>
                                <button type="button" className="btn-primary" onClick={handleSend} disabled={sending || !draft.trim()}>
                                    {sending ? '发送中...' : '发送'}
                                </button>
                            </div>
                        </div>

                        <div className="subsection">
                            <h3>当前会话运行记录</h3>
                            <div className="table-wrap">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>状态</th>
                                            <th>模式</th>
                                            <th>摘要</th>
                                            <th>开始时间</th>
                                            <th>结束时间</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {sessionRuns.map((run) => (
                                            <tr key={run.id}>
                                                <td>{translateRunStatus(run.status)}</td>
                                                <td>{translateScheduleMode(run.schedule_mode)}</td>
                                                <td>{run.result_summary || run.prompt || '--'}</td>
                                                <td>{formatDateTime(run.started_at || run.scheduled_at)}</td>
                                                <td>{formatDateTime(run.finished_at)}</td>
                                            </tr>
                                        ))}
                                        {!sessionRuns.length ? (
                                            <tr>
                                                <td colSpan="5">
                                                    <div className="empty-state">当前会话暂无运行记录。</div>
                                                </td>
                                            </tr>
                                        ) : null}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">待审批</h2>
                            <p className="card-subtitle">处理需要人工确认的动作。</p>
                        </div>
                    </div>
                    <div className="list">
                        {approvals.map((approval) => (
                            <div key={approval.id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{approval.summary || approval.reason || '审批请求'}</div>
                                    <div className="list-row-subtitle">
                                        风险等级 {approval.risk_level || '--'} / 截止 {formatDateTime(approval.expires_at)}
                                    </div>
                                </div>
                                <div className="list-row-meta">
                                    <span className={`status-tag ${approval.status === 'pending' ? 'is-warning' : approval.status === 'approved' ? 'is-success' : 'is-danger'}`}>
                                        {translateApprovalStatus(approval.status)}
                                    </span>
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
                        {!approvals.length ? <div className="empty-state">当前没有审批请求。</div> : null}
                    </div>
                </section>

                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">巡检计划</h2>
                            <p className="card-subtitle">查看、启停或手动执行巡检。</p>
                        </div>
                        {!scheduledTasks.length ? (
                            <button type="button" className="btn-primary" onClick={handleBootstrapDefaults} disabled={bootstrapping}>
                                {bootstrapping ? '初始化中...' : '初始化默认巡检'}
                            </button>
                        ) : null}
                    </div>
                    <div className="list">
                        {scheduledTasks.map((task) => (
                            <div key={task.id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{task.name}</div>
                                    <div className="list-row-subtitle">
                                        {task.description || task.prompt_template || '暂无说明'} / 下次运行 {formatDateTime(task.next_run_at)}
                                    </div>
                                </div>
                                <div className="list-row-meta">
                                    <span className={`status-tag ${task.enabled ? 'is-success' : 'is-warning'}`}>
                                        {task.enabled ? '已启用' : '已停用'}
                                    </span>
                                    <div className="table-actions">
                                        <button
                                            type="button"
                                            className="btn-ghost"
                                            onClick={() => handleTaskTrigger(task.id)}
                                            disabled={taskSubmittingId === `trigger:${task.id}`}
                                        >
                                            立即执行
                                        </button>
                                        <button
                                            type="button"
                                            className="btn-ghost"
                                            onClick={() => handleTaskToggle(task)}
                                            disabled={taskSubmittingId === `toggle:${task.id}`}
                                        >
                                            {task.enabled ? '停用' : '启用'}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                        {!scheduledTasks.length ? <div className="empty-state">当前没有巡检计划。</div> : null}
                    </div>
                </section>
            </div>

            <div className="page-grid-2">
                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">运行时告警</h2>
                            <p className="card-subtitle">查看循环异常和恢复情况。</p>
                        </div>
                    </div>
                    <div className="list">
                        {runtimeAlerts.map((alert) => (
                            <div key={alert.id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{alert.summary}</div>
                                    <div className="list-row-subtitle">{alert.evidence_summary || alert.source_rule || '暂无详情'}</div>
                                </div>
                                <div className="list-row-meta">
                                    <span className={`status-tag ${alert.status === 'resolved' ? 'is-success' : 'is-danger'}`}>
                                        {translateAlertStatus(alert.status)}
                                    </span>
                                    <span className="status-tag is-warning">{translateSeverity(alert.severity)}</span>
                                    <span>{formatDateTime(alert.updated_at || alert.detected_at)}</span>
                                </div>
                            </div>
                        ))}
                        {!runtimeAlerts.length ? <div className="empty-state">当前没有运行时告警。</div> : null}
                    </div>
                </section>

                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">告警邮件订阅</h2>
                            <p className="card-subtitle">把智能体运行告警实时发到指定邮箱。</p>
                        </div>
                    </div>
                    <div className="field-grid three">
                        <label className="field">
                            <span>邮箱</span>
                            <input
                                type="email"
                                value={subscriptionEmail}
                                onChange={(event) => setSubscriptionEmail(event.target.value)}
                                placeholder="ops@example.com"
                            />
                        </label>
                        <label className="field">
                            <span>告警级别</span>
                            <select value={subscriptionSeverity} onChange={(event) => setSubscriptionSeverity(event.target.value)}>
                                {SUBSCRIPTION_SEVERITY_OPTIONS.map((option) => (
                                    <option key={option.key} value={option.key}>
                                        {option.label}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <div className="field action-field">
                            <span>新增订阅</span>
                            <button
                                type="button"
                                className="btn-primary"
                                onClick={handleCreateSubscription}
                                disabled={subscriptionSubmittingId === 'create' || !subscriptionEmail.trim()}
                            >
                                {subscriptionSubmittingId === 'create' ? '提交中...' : '新增'}
                            </button>
                        </div>
                    </div>
                    <div className="list">
                        {subscriptions.map((subscription) => (
                            <div key={subscription.id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{subscription.target}</div>
                                    <div className="list-row-subtitle">
                                        {translateChannel(subscription.channel)} / {translateScheduleType(subscription.schedule_type)} / {translateSeverity(subscription.severity_floor)}
                                    </div>
                                </div>
                                <div className="list-row-meta">
                                    <span className={`status-tag ${subscription.enabled ? 'is-success' : 'is-warning'}`}>
                                        {subscription.enabled ? '已启用' : '已停用'}
                                    </span>
                                    <div className="table-actions">
                                        <button
                                            type="button"
                                            className="btn-ghost"
                                            onClick={() => handleSubscriptionToggle(subscription)}
                                            disabled={subscriptionSubmittingId === `toggle:${subscription.id}`}
                                        >
                                            {subscription.enabled ? '停用' : '启用'}
                                        </button>
                                        <button
                                            type="button"
                                            className="btn-ghost danger"
                                            onClick={() => handleSubscriptionDelete(subscription.id)}
                                            disabled={subscriptionSubmittingId === `delete:${subscription.id}`}
                                        >
                                            删除
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                        {!subscriptions.length ? <div className="empty-state">当前没有邮件订阅。</div> : null}
                    </div>
                </section>
            </div>

            {loading ? <div className="empty-state">正在加载智能体工作台...</div> : null}
        </div>
    );
}

export default AgentConsoleSimple;
