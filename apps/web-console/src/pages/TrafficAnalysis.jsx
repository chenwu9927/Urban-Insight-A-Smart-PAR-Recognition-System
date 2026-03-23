import { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../lib/api';

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

function TrafficAnalysis() {
    const location = useLocation();
    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(location.state?.fileId || '');
    const [loading, setLoading] = useState(false);
    const [stats, setStats] = useState(null);
    const [interval, setInterval] = useState(5);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchFiles = async () => {
            try {
                const response = await api.get('/files');
                setFiles((response.data || []).filter((file) => file.status === 'analyzed'));
            } catch (loadError) {
                console.error('Failed to fetch files', loadError);
                setError('已分析文件列表加载失败。');
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
            setStats(response.data);
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

    return (
        <div className="page-shell">
            <section className="page-header">
                <div className="page-title-group">
                    <span>分析</span>
                    <h1>客流分析</h1>
                    <p>选择一个已经分析完成的文件，按时间粒度查看人数变化和结构分布。</p>
                </div>
                <div className="page-header-actions">
                    <button type="button" className="btn-primary" onClick={analyzeTraffic} disabled={!selectedFile || loading}>
                        {loading ? '生成中...' : '生成报告'}
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
                        <span>统计间隔</span>
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
                    <section className="card">
                        <div className="card-header">
                            <div>
                                <h2 className="card-title">人数趋势</h2>
                                <p className="card-subtitle">查看不同时间段的人流变化。</p>
                            </div>
                        </div>
                        <div className="chart-box">
                            <ResponsiveContainer width="100%" height={320}>
                                <AreaChart data={stats.traffic_trend || []}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="time" />
                                    <YAxis />
                                    <Tooltip />
                                    <Area type="monotone" dataKey="count" stroke="#8f6b52" fill="#d9c4b1" fillOpacity={0.55} />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </section>

                    <div className="page-grid-2">
                        <section className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">性别分布</h2>
                                    <p className="card-subtitle">基于当前文件的识别结果。</p>
                                </div>
                            </div>
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
                        </section>

                        <section className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">年龄分布</h2>
                                    <p className="card-subtitle">按年龄段汇总占比。</p>
                                </div>
                            </div>
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
                        </section>
                    </div>
                </>
            ) : null}
        </div>
    );
}

export default TrafficAnalysis;
