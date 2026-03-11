import { useEffect, useState } from 'react';
import { Users, Activity, Clock, Database, Calendar, Sparkles, AlertTriangle } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../lib/api';

const StatCard = ({ label, value, icon: Icon, color }) => (
    <div className="stat-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
            <div>
                <p className="stat-label">{label}</p>
                <p className="stat-value">{value}</p>
            </div>
            <div style={{ background: color + '20', borderRadius: '8px', padding: '8px', color: color }}>
                <Icon size={24} />
            </div>
        </div>
    </div>
);

const Dashboard = () => {
    const [stats, setStats] = useState({
        total_analyses: 0,
        total_pedestrians: 0,
        gender_distribution: {},
        age_distribution: {},
        traffic_trend: [],
        storage_used: '0 B'
    });

    const [brief, setBrief] = useState(null);
    const [briefLoading, setBriefLoading] = useState(false);
    const [briefError, setBriefError] = useState('');
    const [useLLM, setUseLLM] = useState(true);

    // 默认日期为今天
    const today = new Date().toISOString().slice(0, 10);
    const [selectedDate, setSelectedDate] = useState(today);

    const fetchStats = async (date) => {
        try {
            const url = date
                ? `/stats?date=${date}`
                : '/stats';
            const res = await api.get(url);
            setStats(res.data);
        } catch (err) {
            console.error("Failed to fetch stats", err);
        }
    };

    const fetchBrief = async (date) => {
        setBriefLoading(true);
        setBriefError('');
        try {
            const url = `/insights/brief?date=${date}&use_llm=${useLLM ? 1 : 0}&cache=1`;
            const res = await api.get(url);
            setBrief(res.data);
        } catch (err) {
            console.error("Failed to fetch brief", err);
            setBriefError('获取简报失败');
        } finally {
            setBriefLoading(false);
        }
    };

    useEffect(() => {
        fetchStats(selectedDate);
        fetchBrief(selectedDate);
    }, [selectedDate]);

    useEffect(() => {
        fetchBrief(selectedDate);
    }, [useLLM]);

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>系统概览</h1>
            <div className="stat-grid">
                <StatCard label="总分析次数" value={stats.total_analyses} icon={Activity} color="#2563eb" />
                <StatCard label="累计识别行人" value={stats.total_pedestrians} icon={Users} color="#10b981" />
                <StatCard label="系统运行时间" value="24h" icon={Clock} color="#f59e0b" />
                <StatCard label="存储占用" value={stats.storage_used || '0 B'} icon={Database} color="#6366f1" />
            </div>

            <div className="stat-card" style={{ marginBottom: '2rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                    <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Sparkles size={18} color="#2563eb" /> 今日简报
                    </h3>
                    <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', userSelect: 'none', color: '#334155' }}>
                        <input type="checkbox" checked={useLLM} onChange={(e) => setUseLLM(e.target.checked)} />
                        使用LLM（无Key自动降级）
                    </label>
                </div>
                {briefLoading ? (
                    <div style={{ color: '#94a3b8' }}>生成中...</div>
                ) : briefError ? (
                    <div style={{ color: '#991b1b' }}>{briefError}</div>
                ) : brief ? (
                    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
                        <div>
                            <div style={{ color: '#0f172a', lineHeight: 1.8 }}>{brief.summary || '暂无摘要'}</div>
                            <ul style={{ margin: '0.75rem 0 0', paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                                {(brief.key_findings || []).length ? (brief.key_findings || []).map((x, i) => <li key={i}>{x}</li>) : <li>暂无关键发现</li>}
                            </ul>
                            <div style={{ marginTop: '0.75rem', color: '#475569', fontSize: '0.9rem' }}>
                                方式：{brief.llm_used ? 'LLM' : '规则'} {brief.cached ? '（缓存命中）' : ''}
                            </div>
                        </div>
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                                <AlertTriangle size={16} color="#f59e0b" />
                                <div style={{ fontWeight: 700, color: '#0f172a' }}>告警</div>
                            </div>
                            {(brief.alerts || []).length ? (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                                    {(brief.alerts || []).slice(0, 3).map((a, i) => (
                                        <div key={i} style={{ padding: '0.75rem', borderRadius: '0.75rem', border: '1px solid #e2e8f0' }}>
                                            <div style={{ fontWeight: 700, color: '#0f172a' }}>
                                                {a.title} <span style={{ color: '#64748b', fontWeight: 600 }}>({a.level})</span>
                                            </div>
                                            <div style={{ color: '#334155', marginTop: '0.25rem', lineHeight: 1.6 }}>{a.detail}</div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div style={{ color: '#94a3b8' }}>暂无告警</div>
                            )}
                        </div>
                    </div>
                ) : null}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
                {/* Traffic Chart */}
                <div className="stat-card" style={{ height: '400px', display: 'flex', flexDirection: 'column' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                        <h3 style={{ margin: 0 }}>全天客流趋势</h3>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Calendar size={16} color="#64748b" />
                            <input
                                type="date"
                                value={selectedDate}
                                onChange={(e) => setSelectedDate(e.target.value)}
                                style={{ padding: '0.4rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1', fontSize: '0.9rem' }}
                            />
                        </div>
                    </div>
                    {stats.traffic_trend && stats.traffic_trend.length > 0 ? (
                        <div style={{ flex: 1 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart
                                    data={stats.traffic_trend}
                                    margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                                >
                                    <defs>
                                        <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#2563eb" stopOpacity={0.1} />
                                            <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="time" />
                                    <YAxis />
                                    <Tooltip />
                                    <Area type="monotone" dataKey="count" stroke="#2563eb" fillOpacity={1} fill="url(#colorCount)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#94a3b8' }}>
                            Loading Chart...
                        </div>
                    )}
                </div>

                {/* Gender Dist */}
                <div className="stat-card">
                    <h3>性别分布</h3>
                    {Object.entries(stats.gender_distribution).map(([key, value]) => (
                        <div key={key} style={{ marginTop: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                                <span>{key}</span>
                                <span>{value}%</span>
                            </div>
                            <div style={{ width: '100%', height: '8px', background: '#f1f5f9', borderRadius: '4px' }}>
                                <div style={{ width: `${value}%`, height: '100%', background: '#2563eb', borderRadius: '4px' }}></div>
                            </div>
                        </div>
                    ))}

                    <h3 style={{ marginTop: '2rem' }}>年龄分布</h3>
                    {Object.entries(stats.age_distribution).map(([key, value]) => (
                        <div key={key} style={{ marginTop: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                                <span>{key}</span>
                                <span>{value}%</span>
                            </div>
                            <div style={{ width: '100%', height: '8px', background: '#f1f5f9', borderRadius: '4px' }}>
                                <div style={{ width: `${value}%`, height: '100%', background: '#10b981', borderRadius: '4px' }}></div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default Dashboard;
