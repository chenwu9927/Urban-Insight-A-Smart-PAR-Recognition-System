import { useEffect, useState } from 'react';
import axios from 'axios';
import { Users, Activity, Clock, Database, Calendar } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

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

    // 默认日期为今天
    const today = new Date().toISOString().slice(0, 10);
    const [selectedDate, setSelectedDate] = useState(today);

    const fetchStats = async (date) => {
        try {
            const url = date
                ? `http://localhost:8000/stats?date=${date}`
                : 'http://localhost:8000/stats';
            const res = await axios.get(url);
            setStats(res.data);
        } catch (err) {
            console.error("Failed to fetch stats", err);
        }
    };

    useEffect(() => {
        fetchStats(selectedDate);
    }, [selectedDate]);

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>系统概览</h1>
            <div className="stat-grid">
                <StatCard label="总分析次数" value={stats.total_analyses} icon={Activity} color="#2563eb" />
                <StatCard label="累计识别行人" value={stats.total_pedestrians} icon={Users} color="#10b981" />
                <StatCard label="系统运行时间" value="24h" icon={Clock} color="#f59e0b" />
                <StatCard label="存储占用" value={stats.storage_used || '0 B'} icon={Database} color="#6366f1" />
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
