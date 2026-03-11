import { useEffect, useState } from 'react';
import { Trash2, FileText, RefreshCw } from 'lucide-react';
import { api } from '../lib/api';

const History = () => {
    const [records, setRecords] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [report, setReport] = useState(null);
    const [reportLoading, setReportLoading] = useState(false);
    const [reportError, setReportError] = useState('');
    const [useLLM, setUseLLM] = useState(true);

    const fetchHistory = async () => {
        try {
            const res = await api.get('/history');
            setRecords(res.data);
        } catch (err) {
            console.error("Failed to fetch history", err);
        }
    };

    useEffect(() => {
        fetchHistory();
    }, []);

    const handleDelete = async (id) => {
        if (!confirm("确定删除此记录吗？")) return;
        try {
            await api.delete(`/history/${id}`);
            setRecords(records.filter(r => r.id !== id));
        } catch (err) {
            console.error("Failed to delete", err);
            alert("删除失败");
        }
    };

    const fetchReport = async (id, { refresh = false } = {}) => {
        setSelectedId(id);
        setReport(null);
        setReportError('');
        setReportLoading(true);
        try {
            const url = `/history/${id}/report?use_llm=${useLLM ? 1 : 0}&refresh=${refresh ? 1 : 0}`;
            const res = await api.get(url);
            setReport(res.data);
        } catch (err) {
            console.error(err);
            setReportError('获取报告失败，请稍后重试。');
        } finally {
            setReportLoading(false);
        }
    };

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>历史记录</h1>

            <div className="stat-card" style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ color: '#475569' }}>
                    选择一条记录生成/查看分析报告（默认落库复用）
                </div>
                <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', userSelect: 'none', color: '#334155' }}>
                    <input type="checkbox" checked={useLLM} onChange={(e) => setUseLLM(e.target.checked)} />
                    使用LLM生成报告（无Key自动降级）
                </label>
            </div>
            <div className="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>文件名</th>
                            <th>上传时间</th>
                            <th>识别行人数</th>
                            <th>状态</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {records.map((record) => (
                            <tr key={record.id}>
                                <td>#{record.id}</td>
                                <td>{record.filename}</td>
                                <td>{new Date(record.upload_time).toLocaleString()}</td>
                                <td>
                                    <span style={{ fontWeight: 'bold' }}>{record.pedestrian_count}</span> 人
                                </td>
                                <td>
                                    <span style={{
                                        background: '#dcfce7', color: '#166534',
                                        padding: '0.25rem 0.75rem', borderRadius: '999px', fontSize: '0.875rem'
                                    }}>
                                        完成
                                    </span>
                                </td>
                                <td style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                    <button
                                        onClick={() => fetchReport(record.id)}
                                        style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#2563eb' }}
                                        title="查看报告"
                                    >
                                        <FileText size={16} />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(record.id)}
                                        style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#ef4444' }}
                                        title="删除记录"
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {records.length === 0 && (
                            <tr>
                                <td colSpan="6" style={{ textAlign: 'center', padding: '3rem', color: '#94a3b8' }}>
                                    暂无记录
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {selectedId ? (
                <div className="stat-card" style={{ marginTop: '1.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <h3 style={{ margin: 0 }}>报告：记录 #{selectedId}</h3>
                        <button
                            className="btn-primary"
                            onClick={() => fetchReport(selectedId, { refresh: true })}
                            disabled={reportLoading}
                            style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}
                        >
                            <RefreshCw size={16} />
                            重新生成
                        </button>
                    </div>

                    {reportLoading ? (
                        <div style={{ marginTop: '1rem', color: '#94a3b8' }}>生成中...</div>
                    ) : reportError ? (
                        <div style={{ marginTop: '1rem', color: '#991b1b' }}>{reportError}</div>
                    ) : report ? (
                        <div style={{ marginTop: '1rem', lineHeight: 1.8, color: '#0f172a' }}>
                            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                                <span style={{ padding: '0.2rem 0.6rem', borderRadius: '999px', background: '#eef2ff', color: '#3730a3', fontWeight: 600 }}>
                                    {report.llm_used ? 'LLM' : '规则'}
                                </span>
                                <span style={{ padding: '0.2rem 0.6rem', borderRadius: '999px', background: report.cached ? '#ecfeff' : '#f1f5f9', color: '#0f172a', fontWeight: 600 }}>
                                    {report.cached ? '已落库' : '新生成'}
                                </span>
                            </div>

                            <div style={{ marginBottom: '0.75rem' }}>
                                <div style={{ color: '#334155', fontSize: '0.9rem' }}>摘要</div>
                                <div>{report.report?.summary || '暂无'}</div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                                <div>
                                    <div style={{ color: '#334155', fontSize: '0.9rem' }}>关键发现</div>
                                    <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
                                        {(report.report?.key_findings || []).length ? (report.report.key_findings || []).map((x, i) => <li key={i}>{x}</li>) : <li>暂无</li>}
                                    </ul>
                                </div>
                                <div>
                                    <div style={{ color: '#334155', fontSize: '0.9rem' }}>建议</div>
                                    <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
                                        {(report.report?.recommendations || []).length ? (report.report.recommendations || []).map((x, i) => <li key={i}>{x}</li>) : <li>暂无</li>}
                                    </ul>
                                </div>
                            </div>
                        </div>
                    ) : null}
                </div>
            ) : null}
        </div>
    );
};

export default History;

