import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../lib/api';

function translateGenderLabel(value) {
    const mapping = {
        Male: '男',
        Female: '女',
        Unknown: '未知',
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
        Unknown: '未知',
    };
    return mapping[value] || value || '--';
}

function TrafficAnalysis() {
    const location = useLocation();
    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(location.state?.fileId ? String(location.state.fileId) : '');
    const [interval, setInterval] = useState(5);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchFiles = async () => {
            try {
                const response = await api.get('/files');
                setFiles((response.data || []).filter((file) => file.status === 'analyzed'));
            } catch (loadError) {
                console.error('Failed to fetch files', loadError);
                setError('分析文件列表加载失败。');
            }
        };
        void fetchFiles();
    }, []);

    const analyzeTraffic = useCallback(async () => {
        if (!selectedFile) {
            return;
        }
        setLoading(true);
        setError('');
        try {
            const response = await api.get(`/stats?file_id=${selectedFile}&interval=${interval}`);
            setStats(response.data || null);
        } catch (loadError) {
            console.error('Failed to analyze traffic', loadError);
            setError('客流分析请求失败。');
        } finally {
            setLoading(false);
        }
    }, [interval, selectedFile]);

    useEffect(() => {
        if (selectedFile) {
            void analyzeTraffic();
        }
    }, [analyzeTraffic, selectedFile]);

    const peakPoint = useMemo(() => {
        const trend = stats?.traffic_trend || [];
        if (!trend.length) return null;
        return trend.reduce((best, item) => (item.count > (best?.count ?? -1) ? item : best), null);
    }, [stats]);

    const summaryItems = [
        { label: '总人数', value: stats?.total_pedestrians ?? '--' },
        { label: '时间粒度', value: stats?.interval_minutes ? `${stats.interval_minutes} 分钟` : '--' },
        { label: '存储占用', value: stats?.storage_used ?? '--' },
    ];

    return (
        <div className="page-shell">
            <section className="page-toolbar">
                <div className="page-header-actions">
                    <button type="button" className="btn-primary" onClick={analyzeTraffic} disabled={!selectedFile || loading}>
                        {loading ? '生成中…' : '刷新分析'}
                    </button>
                </div>
            </section>

            {error ? <div className="notice error">{error}</div> : null}

            <section className="card">
                <div className="field-grid two">
                    <label className="field">
                        <span>分析文件</span>
                        <select value={selectedFile} onChange={(event) => setSelectedFile(event.target.value)}>
                            <option value="">请选择文件</option>
                            {files.map((file) => (
                                <option key={file.id} value={file.id}>
                                    {file.filename}
                                </option>
                            ))}
                        </select>
                    </label>

                    <label className="field">
                        <span>统计粒度</span>
                        <select value={interval} onChange={(event) => setInterval(Number(event.target.value))}>
                            <option value={1}>1 分钟</option>
                            <option value={5}>5 分钟</option>
                            <option value={30}>30 分钟</option>
                            <option value={60}>60 分钟</option>
                        </select>
                    </label>
                </div>
            </section>

            {stats ? (
                <>
                    <section className="card subtle-card compact-card">
                        <div className="compact-summary">
                            {summaryItems.map((item) => (
                                <div key={item.label} className="compact-metric">
                                    <span>{item.label}</span>
                                    <strong>{item.value}</strong>
                                </div>
                            ))}
                            <div className="compact-metric is-muted">
                                <span>峰值时段</span>
                                <strong>{peakPoint ? `${peakPoint.time} · ${peakPoint.count}` : '--'}</strong>
                            </div>
                        </div>
                    </section>

                    <section className="card">
                        <div className="list-row-title">人数趋势</div>
                        <div className="chart-box">
                            <ResponsiveContainer width="100%" height={320}>
                                <AreaChart data={stats.traffic_trend || []}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="time" />
                                    <YAxis />
                                    <Tooltip />
                                    <Area type="monotone" dataKey="count" stroke="#4d4d4d" fill="#c9c9c9" fillOpacity={0.55} />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </section>

                    <div className="page-grid-2">
                        <section className="card">
                            <div className="list-row-title">性别分布</div>
                            <div className="meter-list" style={{ marginTop: 12 }}>
                                {Object.entries(stats.gender_distribution || {}).length ? (
                                    Object.entries(stats.gender_distribution || {}).map(([key, value]) => (
                                        <div key={key} className="meter-row">
                                            <div className="meter-row-head">
                                                <span>{translateGenderLabel(key)}</span>
                                                <strong>{value}%</strong>
                                            </div>
                                            <div className="meter-track">
                                                <div className="meter-fill" style={{ width: `${value}%` }} />
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <div className="empty-state compact">暂无数据。</div>
                                )}
                            </div>
                        </section>

                        <section className="card">
                            <div className="list-row-title">年龄分布</div>
                            <div className="meter-list" style={{ marginTop: 12 }}>
                                {Object.entries(stats.age_distribution || {}).length ? (
                                    Object.entries(stats.age_distribution || {}).map(([key, value]) => (
                                        <div key={key} className="meter-row">
                                            <div className="meter-row-head">
                                                <span>{translateAgeLabel(key)}</span>
                                                <strong>{value}%</strong>
                                            </div>
                                            <div className="meter-track">
                                                <div className="meter-fill alt" style={{ width: `${value}%` }} />
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <div className="empty-state compact">暂无数据。</div>
                                )}
                            </div>
                        </section>
                    </div>
                </>
            ) : selectedFile ? null : (
                <section className="card">
                    <div className="empty-state">先选择一个文件。</div>
                </section>
            )}
        </div>
    );
}

export default TrafficAnalysis;
