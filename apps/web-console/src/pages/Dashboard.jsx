import { createElement, useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, Calendar, Clock, Database, Sparkles, Users } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../lib/api';

const StatCard = ({ label, value, icon, color }) => (
    <div className="stat-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
                <p className="stat-label">{label}</p>
                <p className="stat-value">{value}</p>
            </div>
            <div style={{ background: `${color}20`, borderRadius: '8px', padding: '8px', color }}>
                {createElement(icon, { size: 24 })}
            </div>
        </div>
    </div>
);

const Dashboard = () => {
    const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
    const [selectedDate, setSelectedDate] = useState(today);
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
    const [useLLM, setUseLLM] = useState(true);

    const fetchStats = useCallback(async (date) => {
        try {
            const url = date ? `/stats?date=${date}` : '/stats';
            const response = await api.get(url);
            setStats(response.data);
        } catch (error) {
            console.error('Failed to fetch stats', error);
        }
    }, []);

    const fetchBrief = useCallback(async (date, useLlmValue) => {
        setBriefLoading(true);
        setBriefError('');
        try {
            const url = `/insights/brief?date=${date}&use_llm=${useLlmValue ? 1 : 0}&cache=1`;
            const response = await api.get(url);
            setBrief(response.data);
        } catch (error) {
            console.error('Failed to fetch brief', error);
            setBriefError('Failed to load the daily brief.');
        } finally {
            setBriefLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStats(selectedDate);
        fetchBrief(selectedDate, useLLM);
    }, [fetchBrief, fetchStats, selectedDate, useLLM]);

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>System Overview</h1>

            <div className="stat-grid">
                <StatCard label="Total analyses" value={stats.total_analyses} icon={Activity} color="#2563eb" />
                <StatCard label="Recognized pedestrians" value={stats.total_pedestrians} icon={Users} color="#10b981" />
                <StatCard label="Service uptime" value="24h" icon={Clock} color="#f59e0b" />
                <StatCard label="Storage used" value={stats.storage_used || '0 B'} icon={Database} color="#7c3aed" />
            </div>

            <div className="stat-card" style={{ marginBottom: '2rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', gap: '1rem', flexWrap: 'wrap' }}>
                    <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Sparkles size={18} color="#2563eb" />
                        Daily brief
                    </h3>
                    <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', userSelect: 'none', color: '#334155' }}>
                        <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                        Use LLM when available
                    </label>
                </div>

                {briefLoading ? <div style={{ color: '#94a3b8' }}>Generating brief...</div> : null}
                {briefError ? <div style={{ color: '#991b1b' }}>{briefError}</div> : null}

                {!briefLoading && !briefError && brief ? (
                    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
                        <div>
                            <div style={{ color: '#0f172a', lineHeight: 1.8 }}>{brief.summary || 'No summary available.'}</div>
                            <ul style={{ margin: '0.75rem 0 0', paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                                {(brief.key_findings || []).length
                                    ? (brief.key_findings || []).map((item, index) => <li key={index}>{item}</li>)
                                    : <li>No key findings yet.</li>}
                            </ul>
                            <div style={{ marginTop: '0.75rem', color: '#475569', fontSize: '0.9rem' }}>
                                Source: {brief.llm_used ? 'LLM' : 'Rule-based'} {brief.cached ? '(cached)' : ''}
                            </div>
                        </div>

                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                                <AlertTriangle size={16} color="#f59e0b" />
                                <div style={{ fontWeight: 700, color: '#0f172a' }}>Alerts</div>
                            </div>
                            {(brief.alerts || []).length ? (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                                    {(brief.alerts || []).slice(0, 3).map((alert, index) => (
                                        <div key={index} style={{ padding: '0.75rem', borderRadius: '0.75rem', border: '1px solid #e2e8f0' }}>
                                            <div style={{ fontWeight: 700, color: '#0f172a' }}>
                                                {alert.title}{' '}
                                                <span style={{ color: '#64748b', fontWeight: 600 }}>({alert.level})</span>
                                            </div>
                                            <div style={{ color: '#334155', marginTop: '0.25rem', lineHeight: 1.6 }}>{alert.detail}</div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div style={{ color: '#94a3b8' }}>No alerts for this date.</div>
                            )}
                        </div>
                    </div>
                ) : null}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
                <div className="stat-card" style={{ height: '400px', display: 'flex', flexDirection: 'column' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', gap: '1rem', flexWrap: 'wrap' }}>
                        <h3 style={{ margin: 0 }}>Traffic trend</h3>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Calendar size={16} color="#64748b" />
                            <input
                                type="date"
                                value={selectedDate}
                                onChange={(event) => setSelectedDate(event.target.value)}
                                style={{ padding: '0.4rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1', fontSize: '0.9rem' }}
                            />
                        </div>
                    </div>

                    {stats.traffic_trend?.length ? (
                        <div style={{ flex: 1 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={stats.traffic_trend} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                                    <defs>
                                        <linearGradient id="traffic-gradient" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#2563eb" stopOpacity={0.16} />
                                            <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="time" />
                                    <YAxis />
                                    <Tooltip />
                                    <Area type="monotone" dataKey="count" stroke="#2563eb" fillOpacity={1} fill="url(#traffic-gradient)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#94a3b8' }}>
                            No traffic data available yet.
                        </div>
                    )}
                </div>

                <div className="stat-card">
                    <h3>Gender distribution</h3>
                    {Object.entries(stats.gender_distribution || {}).map(([key, value]) => (
                        <div key={key} style={{ marginTop: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                                <span>{key}</span>
                                <span>{value}%</span>
                            </div>
                            <div style={{ width: '100%', height: '8px', background: '#f1f5f9', borderRadius: '4px' }}>
                                <div style={{ width: `${value}%`, height: '100%', background: '#2563eb', borderRadius: '4px' }} />
                            </div>
                        </div>
                    ))}

                    <h3 style={{ marginTop: '2rem' }}>Age distribution</h3>
                    {Object.entries(stats.age_distribution || {}).map(([key, value]) => (
                        <div key={key} style={{ marginTop: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                                <span>{key}</span>
                                <span>{value}%</span>
                            </div>
                            <div style={{ width: '100%', height: '8px', background: '#f1f5f9', borderRadius: '4px' }}>
                                <div style={{ width: `${value}%`, height: '100%', background: '#10b981', borderRadius: '4px' }} />
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default Dashboard;
