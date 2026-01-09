import { useState, useEffect } from 'react';
import axios from 'axios';
import { useLocation } from 'react-router-dom';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from 'recharts';

const TrafficAnalysis = () => {
    const location = useLocation();
    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(location.state?.fileId || '');
    const [loading, setLoading] = useState(false);
    const [stats, setStats] = useState(null);
    const [interval, setInterval] = useState(5); // 默认5分钟

    useEffect(() => {
        const fetchFiles = async () => {
            try {
                const res = await axios.get('http://localhost:8000/files');
                setFiles(res.data.filter(f => f.status === 'analyzed'));
            } catch (err) {
                console.error(err);
            }
        };
        fetchFiles();
    }, []);

    const handleAnalzeTraffic = async () => {
        if (!selectedFile) return;
        setLoading(true);
        // In real world, we would enable fetching stats specifically for this file_id
        // GET /stats?file_id=123
        // For now, reusing global stats mock but let's pretend it's for this file.
        try {
            const res = await axios.get(`http://localhost:8000/stats?file_id=${selectedFile}&interval=${interval}`);
            setStats(res.data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    // Auto-load if file provided via navigation
    useEffect(() => {
        if (selectedFile) {
            handleAnalzeTraffic();
        }
    }, []); // Only on mount/selectedFile change isn't needed if we stick to button, but auto-load is nice. 

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>客流量趋势分析</h1>

            <div className="stat-card" style={{ marginBottom: '2rem', display: 'flex', gap: '1rem', alignItems: 'end' }}>
                <div style={{ flex: 1 }}>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>选择分析源文件</label>
                    <select
                        value={selectedFile}
                        onChange={(e) => setSelectedFile(e.target.value)}
                        style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                    >
                        <option value="">-- 请选择视频/图像文件 --</option>
                        {files.map(f => (
                            <option key={f.id} value={f.id}>{f.filename}</option>
                        ))}
                    </select>
                </div>
                <div style={{ width: '150px' }}>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>时间粒度</label>
                    <select
                        value={interval}
                        onChange={(e) => setInterval(Number(e.target.value))}
                        style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                    >
                        <option value={1}>1 分钟</option>
                        <option value={5}>5 分钟</option>
                        <option value={30}>30 分钟</option>
                        <option value={60}>1 小时</option>
                    </select>
                </div>
                <button
                    className="btn-primary"
                    onClick={handleAnalzeTraffic}
                    disabled={!selectedFile || loading}
                    style={{ height: '42px' }}
                >
                    生成报表
                </button>
            </div>

            {stats && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
                    <div className="stat-card" style={{ height: '400px', gridColumn: '1/-1', display: 'flex', flexDirection: 'column' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>时间段流量趋势</h3>
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
                    </div>

                    <div className="stat-card">
                        <h3>性别比例</h3>
                        {/* Reusing simple bar logic or text for now */}
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
                    </div>

                    <div className="stat-card">
                        <h3>年龄层分布</h3>
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
            )}
        </div>
    );
};

export default TrafficAnalysis;
