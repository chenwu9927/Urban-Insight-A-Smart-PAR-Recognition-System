import { useCallback, useEffect, useState } from 'react';
import { FileText, RefreshCw, Trash2 } from 'lucide-react';
import { api } from '../lib/api';

const badgeStyle = (background, color) => ({
    padding: '0.2rem 0.6rem',
    borderRadius: '999px',
    background,
    color,
    fontWeight: 600,
});

const History = () => {
    const [records, setRecords] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [report, setReport] = useState(null);
    const [reportLoading, setReportLoading] = useState(false);
    const [reportError, setReportError] = useState('');
    const [useLLM, setUseLLM] = useState(true);

    const fetchHistory = useCallback(async () => {
        try {
            const response = await api.get('/history');
            setRecords(response.data);
        } catch (error) {
            console.error('Failed to fetch history', error);
        }
    }, []);

    useEffect(() => {
        fetchHistory();
    }, [fetchHistory]);

    const handleDelete = async (id) => {
        if (!confirm('Delete this analysis record?')) {
            return;
        }
        try {
            await api.delete(`/history/${id}`);
            setRecords((current) => current.filter((record) => record.id !== id));
            if (selectedId === id) {
                setSelectedId(null);
                setReport(null);
                setReportError('');
            }
        } catch (error) {
            console.error('Failed to delete record', error);
            alert('Delete failed.');
        }
    };

    const fetchReport = useCallback(async (id, { refresh = false } = {}) => {
        setSelectedId(id);
        setReport(null);
        setReportError('');
        setReportLoading(true);
        try {
            const url = `/history/${id}/report?use_llm=${useLLM ? 1 : 0}&refresh=${refresh ? 1 : 0}`;
            const response = await api.get(url);
            setReport(response.data);
        } catch (error) {
            console.error('Failed to fetch report', error);
            setReportError('Failed to load the analysis report.');
        } finally {
            setReportLoading(false);
        }
    }, [useLLM]);

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>Analysis History</h1>

            <div
                className="stat-card"
                style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}
            >
                <div style={{ color: '#475569' }}>
                    Pick a completed analysis to inspect its stored report or regenerate it on demand.
                </div>
                <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', userSelect: 'none', color: '#334155' }}>
                    <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                    Use LLM when available
                </label>
            </div>

            <div className="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>File name</th>
                            <th>Uploaded at</th>
                            <th>Pedestrians</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {records.map((record) => (
                            <tr key={record.id}>
                                <td>#{record.id}</td>
                                <td>{record.filename}</td>
                                <td>{new Date(record.upload_time).toLocaleString()}</td>
                                <td>
                                    <strong>{record.pedestrian_count}</strong>
                                </td>
                                <td>
                                    <span style={badgeStyle('#dcfce7', '#166534')}>Completed</span>
                                </td>
                                <td style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                    <button
                                        onClick={() => fetchReport(record.id)}
                                        style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#2563eb' }}
                                        title="Open report"
                                    >
                                        <FileText size={16} />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(record.id)}
                                        style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#ef4444' }}
                                        title="Delete record"
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {!records.length ? (
                            <tr>
                                <td colSpan="6" style={{ textAlign: 'center', padding: '3rem', color: '#94a3b8' }}>
                                    No history records yet.
                                </td>
                            </tr>
                        ) : null}
                    </tbody>
                </table>
            </div>

            {selectedId ? (
                <div className="stat-card" style={{ marginTop: '1.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                        <h3 style={{ margin: 0 }}>Report for record #{selectedId}</h3>
                        <button
                            className="btn-primary"
                            onClick={() => fetchReport(selectedId, { refresh: true })}
                            disabled={reportLoading}
                            style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}
                        >
                            <RefreshCw size={16} />
                            Regenerate
                        </button>
                    </div>

                    {reportLoading ? <div style={{ marginTop: '1rem', color: '#94a3b8' }}>Generating report...</div> : null}
                    {reportError ? <div style={{ marginTop: '1rem', color: '#991b1b' }}>{reportError}</div> : null}

                    {!reportLoading && !reportError && report ? (
                        <div style={{ marginTop: '1rem', lineHeight: 1.8, color: '#0f172a' }}>
                            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                                <span style={badgeStyle('#eef2ff', '#3730a3')}>{report.llm_used ? 'LLM' : 'Rule-based'}</span>
                                <span style={badgeStyle(report.cached ? '#ecfeff' : '#f1f5f9', '#0f172a')}>
                                    {report.cached ? 'Cached' : 'Fresh'}
                                </span>
                            </div>

                            <div style={{ marginBottom: '0.75rem' }}>
                                <div style={{ color: '#334155', fontSize: '0.9rem' }}>Summary</div>
                                <div>{report.report?.summary || 'No summary available.'}</div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                                <div>
                                    <div style={{ color: '#334155', fontSize: '0.9rem' }}>Key findings</div>
                                    <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
                                        {(report.report?.key_findings || []).length
                                            ? report.report.key_findings.map((item, index) => <li key={index}>{item}</li>)
                                            : <li>No findings available.</li>}
                                    </ul>
                                </div>
                                <div>
                                    <div style={{ color: '#334155', fontSize: '0.9rem' }}>Recommendations</div>
                                    <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
                                        {(report.report?.recommendations || []).length
                                            ? report.report.recommendations.map((item, index) => <li key={index}>{item}</li>)
                                            : <li>No recommendations available.</li>}
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
