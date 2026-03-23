import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';

function History() {
    const [records, setRecords] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [report, setReport] = useState(null);
    const [reportLoading, setReportLoading] = useState(false);
    const [reportError, setReportError] = useState('');
    const [useLLM, setUseLLM] = useState(true);

    const fetchHistory = useCallback(async () => {
        try {
            const response = await api.get('/history');
            setRecords(response.data || []);
        } catch (error) {
            console.error('Failed to fetch history', error);
        }
    }, []);

    useEffect(() => {
        void fetchHistory();
    }, [fetchHistory]);

    const handleDelete = async (id) => {
        if (!window.confirm('确定删除这条分析记录吗？')) {
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
            window.alert('删除失败。');
        }
    };

    const fetchReport = useCallback(
        async (id, { refresh = false } = {}) => {
            setSelectedId(id);
            setReport(null);
            setReportError('');
            setReportLoading(true);
            try {
                const response = await api.get(`/history/${id}/report?use_llm=${useLLM ? 1 : 0}&refresh=${refresh ? 1 : 0}`);
                setReport(response.data);
            } catch (error) {
                console.error('Failed to fetch report', error);
                setReportError('报告加载失败。');
            } finally {
                setReportLoading(false);
            }
        },
        [useLLM],
    );

    return (
        <div className="page-shell">
            <section className="page-header">
                <div className="page-title-group">
                    <span>历史</span>
                    <h1>分析记录</h1>
                    <p>查看已完成的分析记录，并按需重新生成报告。</p>
                </div>
                <div className="page-header-actions">
                    <label className="checkbox-field">
                        <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                        <span>生成报告时使用模型</span>
                    </label>
                </div>
            </section>

            <section className="card">
                <div className="card-header">
                    <div>
                        <h2 className="card-title">记录列表</h2>
                        <p className="card-subtitle">点击查看报告，或删除不再需要的历史数据。</p>
                    </div>
                </div>

                <div className="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>文件名</th>
                                <th>上传时间</th>
                                <th>行人数</th>
                                <th>状态</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {records.map((record) => (
                                <tr key={record.id}>
                                    <td>#{record.id}</td>
                                    <td>{record.filename}</td>
                                    <td>{new Date(record.upload_time).toLocaleString('zh-CN')}</td>
                                    <td>{record.pedestrian_count}</td>
                                    <td>
                                        <span className="status-tag is-success">已完成</span>
                                    </td>
                                    <td>
                                        <div className="table-actions">
                                            <button type="button" className="btn-ghost" onClick={() => fetchReport(record.id)}>
                                                查看报告
                                            </button>
                                            <button type="button" className="btn-ghost danger" onClick={() => handleDelete(record.id)}>
                                                删除
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {!records.length ? (
                                <tr>
                                    <td colSpan="6">
                                        <div className="empty-state">暂无历史记录。</div>
                                    </td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>
            </section>

            {selectedId ? (
                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">记录 #{selectedId} 的报告</h2>
                            <p className="card-subtitle">查看摘要、重点发现和建议。</p>
                        </div>
                        <button type="button" className="btn-primary" onClick={() => fetchReport(selectedId, { refresh: true })} disabled={reportLoading}>
                            {reportLoading ? '生成中...' : '重新生成'}
                        </button>
                    </div>

                    {reportLoading ? <div className="empty-state">正在生成报告...</div> : null}
                    {reportError ? <div className="notice error">{reportError}</div> : null}

                    {!reportLoading && !reportError && report ? (
                        <>
                            <div className="action-row">
                                <span className="status-tag is-info">{report.llm_used ? '模型生成' : '规则生成'}</span>
                                <span className="status-tag is-warning">{report.cached ? '缓存结果' : '实时生成'}</span>
                            </div>

                            <div className="page-grid-2 inner-grid">
                                <div className="card subtle-card">
                                    <h3>摘要</h3>
                                    <p className="prose-block">{report.report?.summary || '暂无摘要。'}</p>
                                </div>
                                <div className="card subtle-card">
                                    <h3>重点发现</h3>
                                    <ul className="simple-list">
                                        {(report.report?.key_findings || []).length ? (
                                            report.report.key_findings.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                                        ) : (
                                            <li>暂无重点发现。</li>
                                        )}
                                    </ul>
                                </div>
                                <div className="card subtle-card">
                                    <h3>建议</h3>
                                    <ul className="simple-list">
                                        {(report.report?.recommendations || []).length ? (
                                            report.report.recommendations.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                                        ) : (
                                            <li>暂无建议。</li>
                                        )}
                                    </ul>
                                </div>
                            </div>
                        </>
                    ) : null}
                </section>
            ) : null}
        </div>
    );
}

export default History;
