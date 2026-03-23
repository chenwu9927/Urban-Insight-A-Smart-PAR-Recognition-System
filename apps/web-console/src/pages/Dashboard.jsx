import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, Bot, FolderOpen, Search, ShieldCheck, Sparkles, TrafficCone } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { agentApi, api } from '../lib/api';

function formatDateTime(value) {
    if (!value) {
        return '--';
    }
    try {
        return new Date(value).toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return value;
    }
}

function translateLoopHealth(value) {
    const mapping = {
        healthy: '正常',
        degraded: '降级',
        failed: '异常',
    };
    return mapping[value] || value || '--';
}

function translateLoopName(value) {
    const mapping = {
        runtime: '运行循环',
        scheduler: '调度循环',
        email: '邮件循环',
    };
    return mapping[value] || value || '--';
}

function translateGenderLabel(value) {
    const mapping = {
        Male: '男',
        Female: '女',
    };
    return mapping[value] || value || '--';
}

function translateAgeLabel(value) {
    const mapping = {
        Child: '儿童',
        Teen: '青少年',
        Young: '青年',
        Adult: '成人',
        Old: '老年',
    };
    return mapping[value] || value || '--';
}

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
    const [overview, setOverview] = useState(null);
    const [runtime, setRuntime] = useState(null);
    const [error, setError] = useState('');

    useEffect(() => {
        let active = true;

        const loadPage = async () => {
            try {
                const [statsResponse, briefResponse, nextOverview, nextRuntime] = await Promise.all([
                    api.get(selectedDate ? `/stats?date=${selectedDate}` : '/stats'),
                    api.get(`/insights/brief?date=${selectedDate}&use_llm=${useLLM ? 1 : 0}&cache=1`),
                    agentApi.overview(),
                    agentApi.runtimeStatus(),
                ]);
                if (!active) {
                    return;
                }
                setStats(statsResponse.data);
                setBrief(briefResponse.data);
                setOverview(nextOverview);
                setRuntime(nextRuntime);
                setError('');
            } catch (loadError) {
                console.error('Failed to load dashboard', loadError);
                if (active) {
                    setError('工作台数据加载失败。');
                }
            }
        };

        void loadPage();
        const timer = window.setInterval(loadPage, 15000);
        return () => {
            active = false;
            window.clearInterval(timer);
        };
    }, [selectedDate, useLLM]);

    const metrics = [
        {
            label: '今日分析任务',
            value: stats.total_analyses ?? 0,
            hint: '当天累计分析量',
            icon: Activity,
        },
        {
            label: '识别到的行人',
            value: stats.total_pedestrians ?? 0,
            hint: '当前数据集中的目标总量',
            icon: Search,
        },
        {
            label: '智能体运行中',
            value: overview?.counts?.active_runs ?? 0,
            hint: '当前正在执行的任务',
            icon: Bot,
        },
        {
            label: '待审批事项',
            value: overview?.counts?.pending_approvals ?? 0,
            hint: '需要人工确认的请求',
            icon: ShieldCheck,
        },
    ];

    const quickLinks = [
        { label: '进入文件库', hint: '上传文件并发起分析', icon: FolderOpen, to: '/files' },
        { label: '进入检索', hint: '按条件、文本或图片查找目标', icon: Search, to: '/retrieval' },
        { label: '查看客流分析', hint: '分析趋势与结构分布', icon: TrafficCone, to: '/traffic' },
        { label: '打开智能体', hint: '直接对话并查看运行状态', icon: Bot, to: '/agent' },
    ];

    return (
        <div className="page-shell">
            <section className="page-header">
                <div className="page-title-group">
                    <span>总览</span>
                    <h1>今日工作台</h1>
                    <p>这里聚合了业务数据、智能体状态和简要结论，便于快速开始当天工作。</p>
                </div>
                <div className="page-header-actions">
                    <label className="field compact-field">
                        <span>日期</span>
                        <input type="date" value={selectedDate} onChange={(event) => setSelectedDate(event.target.value)} />
                    </label>
                    <label className="checkbox-field">
                        <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                        <span>使用模型生成简报</span>
                    </label>
                </div>
            </section>

            {error ? <div className="notice error">{error}</div> : null}

            <section className="stat-grid">
                {metrics.map((item) => {
                    const Icon = item.icon;
                    return (
                        <div key={item.label} className="stat-card">
                            <div className="stat-card-icon">
                                <Icon size={18} />
                            </div>
                            <span className="stat-label">{item.label}</span>
                            <strong className="stat-value">{item.value}</strong>
                            <p className="stat-hint">{item.hint}</p>
                        </div>
                    );
                })}
            </section>

            <section className="card">
                <div className="card-header">
                    <div>
                        <h2 className="card-title">快捷入口</h2>
                        <p className="card-subtitle">保留最常用的入口，减少切换成本。</p>
                    </div>
                </div>
                <div className="link-grid">
                    {quickLinks.map((item) => {
                        const Icon = item.icon;
                        return (
                            <button key={item.label} type="button" className="link-card" onClick={() => navigate(item.to)}>
                                <div className="link-card-icon">
                                    <Icon size={18} />
                                </div>
                                <div>
                                    <strong>{item.label}</strong>
                                    <p>{item.hint}</p>
                                </div>
                            </button>
                        );
                    })}
                </div>
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">智能体状态</h2>
                            <p className="card-subtitle">查看后台循环和当前活跃任务。</p>
                        </div>
                    </div>
                    <div className="list">
                        {Object.entries(runtime?.loops || {}).map(([name, loop]) => (
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
                        {!Object.keys(runtime?.loops || {}).length ? <div className="empty-state">暂无运行状态数据。</div> : null}
                    </div>

                    <div className="subsection">
                        <h3>活跃任务</h3>
                        <div className="list">
                            {(overview?.active_runs || []).slice(0, 5).map((run) => (
                                <div key={run.id} className="list-row">
                                    <div className="list-row-main">
                                        <div className="list-row-title">{run.session_title || '未命名任务'}</div>
                                        <div className="list-row-subtitle">{run.result_summary || run.trigger_text || '正在处理中'}</div>
                                    </div>
                                    <div className="list-row-meta">
                                        <span className="status-tag is-warning">{run.status || '运行中'}</span>
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
                            <h2 className="card-title">今日简报</h2>
                            <p className="card-subtitle">结合洞察服务生成简短结论。</p>
                        </div>
                        <span className="page-chip">
                            <Sparkles size={14} />
                            {brief?.llm_used ? '模型生成' : '规则生成'}
                        </span>
                    </div>

                    <p className="prose-block">{brief?.summary || '暂无简报内容。'}</p>

                    <div className="subsection">
                        <h3>重点发现</h3>
                        <ul className="simple-list">
                            {(brief?.key_findings || []).length ? (
                                brief.key_findings.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                            ) : (
                                <li>暂无重点发现。</li>
                            )}
                        </ul>
                    </div>

                    <div className="subsection">
                        <h3>提醒项</h3>
                        <ul className="simple-list">
                            {(brief?.alerts || []).length ? (
                                brief.alerts.map((item, index) => <li key={`${item.title}-${index}`}>{item.title}：{item.detail}</li>)
                            ) : (
                                <li>暂无提醒项。</li>
                            )}
                        </ul>
                    </div>
                </section>
            </div>

            <div className="page-grid-2">
                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">客流趋势</h2>
                            <p className="card-subtitle">按时间查看人数变化。</p>
                        </div>
                    </div>
                    <div className="chart-box">
                        {stats.traffic_trend?.length ? (
                            <ResponsiveContainer width="100%" height={280}>
                                <AreaChart data={stats.traffic_trend}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="time" />
                                    <YAxis />
                                    <Tooltip />
                                    <Area type="monotone" dataKey="count" stroke="#8f6b52" fill="#d9c4b1" fillOpacity={0.55} />
                                </AreaChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="empty-state">暂无趋势数据。</div>
                        )}
                    </div>
                </section>

                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">人群结构</h2>
                            <p className="card-subtitle">按性别和年龄段查看占比。</p>
                        </div>
                    </div>

                    <div className="subsection">
                        <h3>性别分布</h3>
                        <div className="meter-list">
                            {Object.entries(stats.gender_distribution || {}).map(([key, value]) => (
                                <div key={key} className="meter-row">
                                    <div className="meter-row-head">
                                        <span>{translateGenderLabel(key)}</span>
                                        <strong>{value}%</strong>
                                    </div>
                                    <div className="meter-track">
                                        <div className="meter-fill" style={{ width: `${value}%` }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="subsection">
                        <h3>年龄分布</h3>
                        <div className="meter-list">
                            {Object.entries(stats.age_distribution || {}).map(([key, value]) => (
                                <div key={key} className="meter-row">
                                    <div className="meter-row-head">
                                        <span>{translateAgeLabel(key)}</span>
                                        <strong>{value}%</strong>
                                    </div>
                                    <div className="meter-track">
                                        <div className="meter-fill alt" style={{ width: `${value}%` }} />
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
