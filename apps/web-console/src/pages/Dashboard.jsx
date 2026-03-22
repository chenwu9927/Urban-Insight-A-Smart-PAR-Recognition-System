import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Activity,
    ArrowRight,
    Bot,
    Clock3,
    FolderOpen,
    Search,
    ShieldCheck,
    Sparkles,
    TrafficCone,
    UserRound,
} from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { agentApi, api } from '../lib/api';

const formatDateTime = (value) => {
    if (!value) {
        return 'Not available';
    }
    try {
        return new Date(value).toLocaleString([], {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return value;
    }
};

const metricCards = (stats, overview) => [
    {
        label: 'Analyses today',
        value: stats.total_analyses ?? 0,
        detail: 'Current day processing volume',
        icon: Activity,
        tone: 'blue',
    },
    {
        label: 'Recognized pedestrians',
        value: stats.total_pedestrians ?? 0,
        detail: 'Structured detections in the dataset',
        icon: UserRound,
        tone: 'emerald',
    },
    {
        label: 'Active agent runs',
        value: overview?.counts?.active_runs ?? 0,
        detail: 'Live automation in progress',
        icon: Bot,
        tone: 'amber',
    },
    {
        label: 'Pending approvals',
        value: overview?.counts?.pending_approvals ?? 0,
        detail: 'Human review items waiting',
        icon: ShieldCheck,
        tone: 'rose',
    },
];

const quickActions = [
    {
        title: 'Upload evidence',
        description: 'Bring new videos or images into the library and start analysis.',
        icon: FolderOpen,
        to: '/files',
        tone: 'blue',
    },
    {
        title: 'Search people',
        description: 'Run structured or natural-language retrieval across processed results.',
        icon: Search,
        to: '/retrieval',
        tone: 'teal',
    },
    {
        title: 'Traffic analytics',
        description: 'Inspect pedestrian volume changes and movement patterns.',
        icon: TrafficCone,
        to: '/traffic',
        tone: 'amber',
    },
    {
        title: 'Talk to agent',
        description: 'Assign a task, review its status, and inspect live operational context.',
        icon: Bot,
        to: '/agent',
        tone: 'violet',
    },
];

const toneClassMap = {
    blue: 'is-blue',
    emerald: 'is-emerald',
    amber: 'is-amber',
    rose: 'is-rose',
    teal: 'is-teal',
    violet: 'is-violet',
    slate: 'is-slate',
};

function Dashboard() {
    const navigate = useNavigate();
    const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
    const [selectedDate, setSelectedDate] = useState(today);
    const [useLLM, setUseLLM] = useState(true);
    const [stats, setStats] = useState({
        total_analyses: 0,
        total_pedestrians: 0,
        gender_distribution: {},
        age_distribution: {},
        traffic_trend: [],
        storage_used: '0 B',
    });
    const [brief, setBrief] = useState(null);
    const [briefLoading, setBriefLoading] = useState(false);
    const [briefError, setBriefError] = useState('');
    const [overview, setOverview] = useState(null);
    const [runtime, setRuntime] = useState(null);
    const [systemError, setSystemError] = useState('');

    useEffect(() => {
        let active = true;

        const loadDashboard = async () => {
            try {
                const statsUrl = selectedDate ? `/stats?date=${selectedDate}` : '/stats';
                const response = await api.get(statsUrl);
                if (active) {
                    setStats(response.data);
                }
            } catch (error) {
                console.error('Failed to fetch dashboard stats', error);
            }
        };

        void loadDashboard();
        return () => {
            active = false;
        };
    }, [selectedDate]);

    useEffect(() => {
        let active = true;

        const loadBrief = async () => {
            setBriefLoading(true);
            setBriefError('');
            try {
                const response = await api.get(`/insights/brief?date=${selectedDate}&use_llm=${useLLM ? 1 : 0}&cache=1`);
                if (active) {
                    setBrief(response.data);
                }
            } catch (error) {
                console.error('Failed to fetch daily brief', error);
                if (active) {
                    setBriefError('Daily brief is temporarily unavailable.');
                }
            } finally {
                if (active) {
                    setBriefLoading(false);
                }
            }
        };

        void loadBrief();
        return () => {
            active = false;
        };
    }, [selectedDate, useLLM]);

    useEffect(() => {
        let active = true;

        const loadSystemState = async () => {
            try {
                const [nextOverview, nextRuntime] = await Promise.all([agentApi.overview(), agentApi.runtimeStatus()]);
                if (!active) {
                    return;
                }
                setOverview(nextOverview);
                setRuntime(nextRuntime);
                setSystemError('');
            } catch (error) {
                console.error('Failed to fetch agent runtime state', error);
                if (active) {
                    setSystemError('Agent live status could not be refreshed.');
                }
            }
        };

        void loadSystemState();
        const timer = window.setInterval(loadSystemState, 15000);
        return () => {
            active = false;
            window.clearInterval(timer);
        };
    }, []);

    const cards = metricCards(stats, overview);
    const activeRuns = overview?.active_runs || [];
    const recentSessions = overview?.recent_sessions || [];
    const loopEntries = Object.entries(runtime?.loops || {});

    return (
        <div className="client-dashboard">
            <section className="client-hero">
                <div>
                    <span className="client-eyebrow">Urban Insight Client</span>
                    <h1>Operate analysis, search, and agent workflows from one workspace.</h1>
                    <p>
                        This client view is tuned for day-to-day operations: start a task quickly, watch agent
                        execution, inspect system health, and move straight into retrieval or traffic review.
                    </p>
                    <div className="client-hero-actions">
                        <button type="button" className="btn-primary" onClick={() => navigate('/files')}>
                            Open evidence library
                            <ArrowRight size={16} />
                        </button>
                        <button type="button" className="btn-secondary" onClick={() => navigate('/agent')}>
                            Launch agent workspace
                        </button>
                    </div>
                </div>

                <div className="client-hero-side">
                    <div className="client-hero-badge">
                        <Clock3 size={16} />
                        Live operation mode
                    </div>
                    <div className="client-hero-kpis">
                        <div>
                            <span>Last sync</span>
                            <strong>{formatDateTime(runtime?.started_at)}</strong>
                        </div>
                        <div>
                            <span>Storage</span>
                            <strong>{stats.storage_used || '0 B'}</strong>
                        </div>
                    </div>
                </div>
            </section>

            {systemError ? <div className="agent-banner error">{systemError}</div> : null}

            <section className="client-metric-grid">
                {cards.map((card) => {
                    const Icon = card.icon;
                    return (
                        <div key={card.label} className="client-metric-card">
                            <div className={`client-metric-icon ${toneClassMap[card.tone] || ''}`}>
                                <Icon size={22} />
                            </div>
                            <div className="client-metric-body">
                                <span>{card.label}</span>
                                <strong>{card.value}</strong>
                                <p>{card.detail}</p>
                            </div>
                        </div>
                    );
                })}
            </section>

            <div className="client-dashboard-grid">
                <section className="agent-panel client-quick-actions-panel">
                    <div className="agent-panel-header">
                        <div>
                            <h2>Quick actions</h2>
                            <p>Start the most common operator flows without digging through the menu.</p>
                        </div>
                    </div>
                    <div className="client-quick-grid">
                        {quickActions.map((action) => {
                            const Icon = action.icon;
                            return (
                                <button
                                    key={action.title}
                                    type="button"
                                    className="client-action-tile"
                                    onClick={() => navigate(action.to)}
                                >
                                    <div className={`client-action-icon ${toneClassMap[action.tone] || ''}`}>
                                        <Icon size={20} />
                                    </div>
                                    <div>
                                        <strong>{action.title}</strong>
                                        <p>{action.description}</p>
                                    </div>
                                    <ArrowRight size={16} className="subtle-icon" />
                                </button>
                            );
                        })}
                    </div>
                </section>

                <section className="agent-panel client-runtime-panel">
                    <div className="agent-panel-header">
                        <div>
                            <h2>Agent live board</h2>
                            <p>Immediate visibility into automation health, active work, and recent activity.</p>
                        </div>
                    </div>

                    <div className="client-runtime-section">
                        <h3>Runtime loops</h3>
                        <div className="client-loop-grid">
                            {loopEntries.length ? (
                                loopEntries.map(([name, loop]) => (
                                    <div key={name} className="client-loop-card">
                                        <div className="client-loop-head">
                                            <strong>{name}</strong>
                                            <span className={`status-chip ${loop.health === 'healthy' ? 'is-emerald' : 'is-rose'}`}>
                                                {loop.health}
                                            </span>
                                        </div>
                                        <p>Last heartbeat: {formatDateTime(loop.last_seen_at)}</p>
                                        <p>Restarts: {loop.restart_count ?? 0}</p>
                                    </div>
                                ))
                            ) : (
                                <div className="agent-empty-state">Runtime status is loading.</div>
                            )}
                        </div>
                    </div>

                    <div className="client-runtime-section">
                        <div className="client-section-head">
                            <h3>Active runs</h3>
                            <button type="button" className="btn-ghost" onClick={() => navigate('/agent')}>
                                Open agent center
                            </button>
                        </div>
                        {activeRuns.length ? (
                            <div className="client-run-list">
                                {activeRuns.slice(0, 4).map((run) => (
                                    <div key={run.id} className="client-run-row">
                                        <div>
                                            <strong>{run.session_title || 'Untitled run'}</strong>
                                            <p>{run.trigger_text || run.result_summary || 'Agent is processing this task.'}</p>
                                        </div>
                                        <div className="client-run-meta">
                                            <span>{run.progress ?? 0}%</span>
                                            <span>{run.status}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="agent-empty-state">No live runs at the moment.</div>
                        )}
                    </div>

                    <div className="client-runtime-section">
                        <h3>Recent sessions</h3>
                        {recentSessions.length ? (
                            <div className="client-session-list">
                                {recentSessions.slice(0, 4).map((session) => (
                                    <button
                                        key={session.id}
                                        type="button"
                                        className="client-session-row"
                                        onClick={() => navigate('/agent')}
                                    >
                                        <div>
                                            <strong>{session.title || 'Untitled session'}</strong>
                                            <p>{session.source || 'web'} source</p>
                                        </div>
                                        <span>{formatDateTime(session.updated_at)}</span>
                                    </button>
                                ))}
                            </div>
                        ) : (
                            <div className="agent-empty-state">No recent session activity yet.</div>
                        )}
                    </div>
                </section>
            </div>

            <div className="client-dashboard-grid client-dashboard-grid-secondary">
                <section className="agent-panel client-brief-panel">
                    <div className="agent-panel-header">
                        <div>
                            <h2>Daily brief</h2>
                            <p>Operational summary generated from the selected date and current system insights.</p>
                        </div>
                        <div className="client-brief-controls">
                            <label className="client-llm-toggle">
                                <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                                <span>Use LLM</span>
                            </label>
                            <input
                                type="date"
                                value={selectedDate}
                                onChange={(event) => setSelectedDate(event.target.value)}
                                className="client-date-input"
                            />
                        </div>
                    </div>

                    <div className="client-brief-body">
                        {briefLoading ? <div className="agent-empty-state">Generating today&apos;s brief...</div> : null}
                        {!briefLoading && briefError ? <div className="agent-banner error">{briefError}</div> : null}
                        {!briefLoading && !briefError && brief ? (
                            <>
                                <div className="client-brief-summary">
                                    <div className="client-brief-icon">
                                        <Sparkles size={20} />
                                    </div>
                                    <div>
                                        <strong>{brief.llm_used ? 'LLM-assisted brief' : 'Rule-based brief'}</strong>
                                        <p>{brief.summary || 'No summary available for the selected date.'}</p>
                                    </div>
                                </div>
                                <div className="client-brief-columns">
                                    <div className="client-brief-box">
                                        <h3>Key findings</h3>
                                        <div className="client-bullet-list">
                                            {(brief.key_findings || []).length ? (
                                                (brief.key_findings || []).map((item, index) => (
                                                    <div key={`${item}-${index}`} className="client-bullet-item">
                                                        <span className="client-bullet-dot" />
                                                        <p>{item}</p>
                                                    </div>
                                                ))
                                            ) : (
                                                <div className="agent-empty-state">No key findings for this date.</div>
                                            )}
                                        </div>
                                    </div>
                                    <div className="client-brief-box">
                                        <h3>Alerts</h3>
                                        {(brief.alerts || []).length ? (
                                            <div className="client-alert-list">
                                                {(brief.alerts || []).slice(0, 4).map((alert, index) => (
                                                    <div key={`${alert.title}-${index}`} className="client-alert-row">
                                                        <div className={`client-alert-accent ${alert.level === 'critical' ? 'is-rose' : 'is-amber'}`} />
                                                        <div>
                                                            <strong>{alert.title}</strong>
                                                            <p>{alert.detail}</p>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : (
                                            <div className="agent-empty-state">No alert items in the current brief.</div>
                                        )}
                                    </div>
                                </div>
                            </>
                        ) : null}
                    </div>
                </section>

                <section className="agent-panel client-insight-panel">
                    <div className="agent-panel-header">
                        <div>
                            <h2>Flow and audience snapshot</h2>
                            <p>High-level movement volume and profile mix for rapid operational review.</p>
                        </div>
                    </div>

                    <div className="client-chart-wrap">
                        {stats.traffic_trend?.length ? (
                            <ResponsiveContainer width="100%" height={260}>
                                <AreaChart data={stats.traffic_trend} margin={{ top: 12, right: 20, left: 0, bottom: 0 }}>
                                    <defs>
                                        <linearGradient id="traffic-gradient-client" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#0f766e" stopOpacity={0.28} />
                                            <stop offset="95%" stopColor="#0f766e" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="time" />
                                    <YAxis />
                                    <Tooltip />
                                    <Area
                                        type="monotone"
                                        dataKey="count"
                                        stroke="#0f766e"
                                        fillOpacity={1}
                                        fill="url(#traffic-gradient-client)"
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="agent-empty-state spacious">Traffic data is not available yet.</div>
                        )}
                    </div>

                    <div className="client-profile-grid">
                        <div className="client-profile-card">
                            <h3>Gender distribution</h3>
                            {Object.entries(stats.gender_distribution || {}).map(([key, value]) => (
                                <div key={key} className="client-meter-row">
                                    <div className="client-meter-head">
                                        <span>{key}</span>
                                        <strong>{value}%</strong>
                                    </div>
                                    <div className="client-meter-track">
                                        <div className="client-meter-fill is-blue" style={{ width: `${value}%` }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="client-profile-card">
                            <h3>Age distribution</h3>
                            {Object.entries(stats.age_distribution || {}).map(([key, value]) => (
                                <div key={key} className="client-meter-row">
                                    <div className="client-meter-head">
                                        <span>{key}</span>
                                        <strong>{value}%</strong>
                                    </div>
                                    <div className="client-meter-track">
                                        <div className="client-meter-fill is-emerald" style={{ width: `${value}%` }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>
            </div>
        </div>
    );
}

export default Dashboard;
