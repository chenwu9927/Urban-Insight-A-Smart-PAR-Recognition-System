import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { api } from '../lib/api';
import { formatDateTime } from '../lib/time';

function History() {
    const location = useLocation();
    const [records, setRecords] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [report, setReport] = useState(null);
    const [reportLoading, setReportLoading] = useState(false);
    const [reportError, setReportError] = useState('');
    const [historyError, setHistoryError] = useState('');
    const [useLLM, setUseLLM] = useState(true);
    const targetRecordId = Number(location.state?.recordId) || null;

    const fetchHistory = useCallback(async () => {
        try {
            const response = await api.get('/history');
            setRecords(response.data || []);
            setHistoryError('');
        } catch (error) {
            console.error('Failed to fetch history', error);
            setHistoryError('分析记录加载失败。');
        }
    }, []);

    useEffect(() => {
        void fetchHistory();
    }, [fetchHistory]);

    const fetchReport = useCallback(
        async (id, { refresh = false, llmEnabled = useLLM } = {}) => {
            setSelectedId(id);
            setReport(null);
            setReportError('');
            setReportLoading(true);
            try {
                const response = await api.get(`/history/${id}/report?use_llm=${llmEnabled ? 1 : 0}&refresh=${refresh ? 1 : 0}`);
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

    useEffect(() => {
        if (!targetRecordId || !records.some((record) => record.id === targetRecordId) || selectedId === targetRecordId) {
            return;
        }
        void fetchReport(targetRecordId);
    }, [fetchReport, records, selectedId, targetRecordId]);

    const handleUseLLMChange = (checked) => {
        setUseLLM(checked);
        if (selectedId) {
            void fetchReport(selectedId, { llmEnabled: checked });
        }
    };

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
            {
                label: '结果数',
                value:
                    report.report?.meta?.pedestrian_count ||
                    report.report?.meta?.semantic_result_count ||
                    report.report?.meta?.window_summary_count ||
                    '--',
            },
            { label: '重点发现', value: report.report?.key_findings?.length ?? 0 },
            { label: '异常项', value: report.report?.anomalies?.length ?? 0 },
        ];
    }, [report]);

    return (
        <div className="page-shell">
            {historyError ? <div className="notice error">{historyError}</div> : null}
            <div className="page-grid-2">
                <section className="card">
                    <div className="list-row-title">分析记录</div>
                    <div className="list compact-list" style={{ marginTop: 12 }}>
                        {records.map((record) => (
                            <div key={record.id} className={`list-row ${selectedId === record.id ? 'selected' : ''}`}>
                                <div className="list-row-main" onClick={() => void fetchReport(record.id)} role="button" tabIndex={0}>
                                    <div className="list-row-title">{record.filename || `记录 #${record.id}`}</div>
                                    <div className="list-row-subtitle">
                                        {formatDateTime(record.upload_time)} · {record.camera_location || '未标注点位'}
                                    </div>
                                </div>
                                <div className="list-row-meta">
                                    <button type="button" className="btn-ghost" onClick={() => void fetchReport(record.id)}>
                                        查看
                                    </button>
                                    <button type="button" className="btn-ghost danger" onClick={() => void handleDelete(record.id)}>
                                        删除
                                    </button>
                                </div>
                            </div>
                        ))}
                        {!records.length ? <div className="empty-state">暂无分析记录。</div> : null}
                    </div>
                </section>

                <section className="card">
                    <div className="card-title-row">
                        <h2 className="card-title">{selectedId ? `记录 #${selectedId}` : '报告预览'}</h2>
                        <div className="table-actions">
                            <label className="checkbox-row">
                                <input type="checkbox" checked={useLLM} onChange={(event) => handleUseLLMChange(event.target.checked)} />
                                <span>使用模型</span>
                            </label>
                            {selectedId ? (
                                <button type="button" className="btn-ghost" onClick={() => void fetchReport(selectedId, { refresh: true })}>
                                    {reportLoading ? '生成中…' : '重新生成'}
                                </button>
                            ) : null}
                        </div>
                    </div>

                    {!selectedId ? <div className="empty-state">选择一条记录后查看报告。</div> : null}
                    {reportLoading ? <div className="empty-state">正在生成报告…</div> : null}
                    {reportError ? <div className="notice error">{reportError}</div> : null}

                    {!reportLoading && !reportError && report?.report ? (
                        <div className="report-stack">
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

                            <section className="brief-panel">
                                <h3>摘要</h3>
                                <p>{report.report.summary || '暂无摘要。'}</p>
                            </section>

                            <section>
                                <h3>重点发现</h3>
                                {(report.report.key_findings || []).length ? (
                                    <ul className="bullet-list">
                                        {report.report.key_findings.map((item, index) => (
                                            <li key={`${item}-${index}`}>{item}</li>
                                        ))}
                                    </ul>
                                ) : (
                                    <div className="empty-state">暂无重点发现。</div>
                                )}
                            </section>

                            <section>
                                <h3>建议动作</h3>
                                {(report.report.recommendations || []).length ? (
                                    <ul className="bullet-list">
                                        {report.report.recommendations.map((item, index) => (
                                            <li key={`${item}-${index}`}>{item}</li>
                                        ))}
                                    </ul>
                                ) : (
                                    <div className="empty-state">暂无建议动作。</div>
                                )}
                            </section>
                        </div>
                    ) : null}
                </section>
            </div>
        </div>
    );
}

export default History;
