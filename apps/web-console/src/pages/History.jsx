import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';

function formatDateTime(value) {
    if (!value) return '--';
    try {
        return new Date(value).toLocaleString('zh-CN');
    } catch {
        return value;
    }
}

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

    const fetchReport = useCallback(
        async (id, { refresh = false } = {}) => {
            setSelectedId(id);
            setReport(null);
            setReportError('');
            setReportLoading(true);
            try {
                const response = await api.get(`/history/${id}/report?use_llm=${useLLM ? 1 : 0}&refresh=${refresh ? 1 : 0}`);
                setReport(response.data || null);
            } catch (error) {
                console.error('Failed to fetch report', error);
                setReportError('报告加载失败。');
            } finally {
                setReportLoading(false);
            }
        },
        [useLLM],
    );

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

    const summaryItems = useMemo(() => {
        if (!report?.report) {
            return [];
        }
        return [
            { label: '行人数', value: report.report?.meta?.pedestrian_count ?? '--' },
            { label: '重点发现', value: report.report?.key_findings?.length ?? 0 },
            { label: '异常项', value: report.report?.anomalies?.length ?? 0 },
        ];
    }, [report]);

    return (
        <div className="page-shell">
            <section className="page-toolbar">
                <div className="page-header-actions">
                    <label className="checkbox-field">
                        <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                        <span>生成报告时使用模型</span>
                    </label>
                </div>
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">记录列表</h2>
                        </div>
                    </div>

                    <div className="list compact-list">
                        {records.map((record) => (
                            <div key={record.id} className={`list-row ${selectedId === record.id ? 'selected' : ''}`}>
                                <div className="list-row-main">
                                    <div className="list-row-title">{record.filename}</div>
                                    <div className="list-row-subtitle">
                                        {formatDateTime(record.upload_time)} · 行人数 {record.pedestrian_count}
                                    </div>
                                </div>
                                <div className="list-row-meta">
                                    <button type="button" className="btn-ghost" onClick={() => fetchReport(record.id)}>
                                        查看
                                    </button>
                                    <button type="button" className="btn-ghost danger" onClick={() => handleDelete(record.id)}>
                                        删除
                                    </button>
                                </div>
                            </div>
                        ))}
                        {!records.length ? <div className="empty-state">暂无历史记录。</div> : null}
                    </div>
                </section>

                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">{selectedId ? `记录 #${selectedId}` : '报告预览'}</h2>
                        </div>
                        {selectedId ? (
                            <button
                                type="button"
                                className="btn-primary"
                                onClick={() => fetchReport(selectedId, { refresh: true })}
                                disabled={reportLoading}
                            >
                                {reportLoading ? '生成中...' : '重新生成'}
                            </button>
                        ) : null}
                    </div>

                    {!selectedId ? <div className="empty-state">选择记录后查看。</div> : null}
                    {reportLoading ? <div className="empty-state">正在生成报告...</div> : null}
                    {reportError ? <div className="notice error">{reportError}</div> : null}

                    {!reportLoading && !reportError && report?.report ? (
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
                                        <span>生成方式</span>
                                        <strong>{report.llm_used ? '模型' : '规则'}</strong>
                                    </div>
                                </div>
                            </section>

                            <div className="brief-panel">
                                <p className="prose-block">{report.report.summary || '当前没有可展示的摘要。'}</p>
                            </div>

                            <div className="page-grid-2 inner-grid">
                                <div className="card subtle-card">
                                    <h3>重点发现</h3>
                                    <ul className="simple-list">
                                        {(report.report.key_findings || []).length ? (
                                            report.report.key_findings.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                                        ) : (
                                            <li>暂无重点发现。</li>
                                        )}
                                    </ul>
                                </div>
                                <div className="card subtle-card">
                                    <h3>建议动作</h3>
                                    <ul className="simple-list">
                                        {(report.report.recommendations || []).length ? (
                                            report.report.recommendations.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                                        ) : (
                                            <li>暂无建议动作。</li>
                                        )}
                                    </ul>
                                </div>
                            </div>
                        </>
                    ) : null}
                </section>
            </div>
        </div>
    );
}

export default History;
