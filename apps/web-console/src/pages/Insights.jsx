import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';
import { formatDateInputValue } from '../lib/time';

function formatDateLabel(value) {
    if (!value) return '--';
    try {
        return new Date(value).toLocaleDateString('zh-CN');
    } catch {
        return value;
    }
}

function Insights() {
    const today = useMemo(() => formatDateInputValue(new Date()), []);
    const [selectedDate, setSelectedDate] = useState(today);
    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState('');
    const [useLLM, setUseLLM] = useState(true);
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [question, setQuestion] = useState('');
    const [askLoading, setAskLoading] = useState(false);
    const [askError, setAskError] = useState('');
    const [askData, setAskData] = useState(null);

    useEffect(() => {
        const fetchFiles = async () => {
            try {
                const response = await api.get('/files');
                setFiles((response.data || []).filter((file) => file.status === 'analyzed'));
            } catch (loadError) {
                console.error('Failed to load analyzed files', loadError);
            }
        };
        void fetchFiles();
    }, []);

    const fetchInsights = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const params = new URLSearchParams();
            params.set('interval', '60');
            params.set('use_llm', useLLM ? '1' : '0');
            params.set('cache', '1');
            if (selectedFile) {
                params.set('file_id', String(selectedFile));
            } else {
                params.set('date', selectedDate);
            }
            const response = await api.get(`/insights?${params.toString()}`);
            setData(response.data || null);
        } catch (loadError) {
            console.error('Failed to fetch insights', loadError);
            setError('智能研判加载失败。');
        } finally {
            setLoading(false);
        }
    }, [selectedDate, selectedFile, useLLM]);

    useEffect(() => {
        void fetchInsights();
    }, [fetchInsights]);

    const askQuestion = async () => {
        const trimmed = question.trim();
        if (!trimmed) {
            return;
        }
        setAskLoading(true);
        setAskError('');
        try {
            const payload = {
                question: trimmed,
                interval: 60,
                use_llm: useLLM ? 1 : 0,
                cache: 1,
            };
            if (selectedFile) {
                payload.file_id = Number(selectedFile);
            } else {
                payload.date = selectedDate;
            }
            const response = await api.post('/insights/ask', payload);
            setAskData(response.data || null);
        } catch (askFailure) {
            console.error('Failed to ask insight question', askFailure);
            setAskError('提问失败。');
        } finally {
            setAskLoading(false);
        }
    };

    const summaryItems = [
        { label: '行人数', value: data?.stats?.total_pedestrians ?? '--' },
        { label: '重点发现', value: data?.key_findings?.length ?? 0 },
        { label: '异常项', value: data?.anomalies?.length ?? 0 },
    ];

    const focusItems = data?.key_findings?.length ? data.key_findings : ['当前没有新的重点发现。'];
    const actionItems = data?.recommendations?.length ? data.recommendations : ['当前没有需要追加的动作。'];
    const followupItems = data?.questions?.length ? data.questions : data?.anomalies?.length ? data.anomalies : ['暂无待跟进问题。'];

    return (
        <div className="page-shell">
            <section className="page-toolbar">
                <div className="page-header-actions">
                    <button type="button" className="btn-primary" onClick={fetchInsights} disabled={loading}>
                        {loading ? '更新中…' : '刷新研判'}
                    </button>
                </div>
            </section>

            <section className="card">
                <div className="field-grid three">
                    <label className="field">
                        <span>范围</span>
                        <select value={selectedFile} onChange={(event) => setSelectedFile(event.target.value)}>
                            <option value="">按日期汇总</option>
                            {files.map((file) => (
                                <option key={file.id} value={file.id}>
                                    {file.filename}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className="field">
                        <span>日期</span>
                        <input
                            type="date"
                            value={selectedDate}
                            disabled={Boolean(selectedFile)}
                            onChange={(event) => setSelectedDate(event.target.value)}
                        />
                    </label>
                    <label className="checkbox-field">
                        <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                        <span>使用模型生成研判</span>
                    </label>
                </div>
            </section>

            {error ? <div className="notice error">{error}</div> : null}

            {data ? (
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
                                <strong>{data.llm_used ? '模型' : '规则'}</strong>
                            </div>
                        </div>
                    </section>

                    <section className="card">
                        <div className="list-row-title">一句结论</div>
                        <div className="brief-panel" style={{ marginTop: 12 }}>
                            <p className="prose-block">{data.summary || '当前没有可展示的摘要。'}</p>
                            <div className="list-row-subtitle">{selectedFile ? '当前文件' : formatDateLabel(data.scope?.date)}</div>
                        </div>
                    </section>

                    <div className="page-grid-2">
                        <section className="card">
                            <div className="list-row-title">重点</div>
                            <ul className="simple-list" style={{ marginTop: 12 }}>
                                {focusItems.map((item, index) => (
                                    <li key={`${item}-${index}`}>{item}</li>
                                ))}
                            </ul>
                        </section>

                        <section className="card">
                            <div className="list-row-title">建议动作</div>
                            <ul className="simple-list" style={{ marginTop: 12 }}>
                                {actionItems.map((item, index) => (
                                    <li key={`${item}-${index}`}>{item}</li>
                                ))}
                            </ul>
                        </section>
                    </div>

                    <section className="card">
                        <div className="list-row-title">继续追问</div>
                        <div className="field-grid one" style={{ marginTop: 12 }}>
                            <label className="field">
                                <span>问题</span>
                                <textarea
                                    value={question}
                                    onChange={(event) => setQuestion(event.target.value)}
                                    placeholder="例如：这批异常里最值得先核查的是哪一项？"
                                />
                            </label>
                        </div>

                        <div className="action-row">
                            <button type="button" className="btn-primary" onClick={askQuestion} disabled={askLoading || !question.trim()}>
                                {askLoading ? '处理中…' : '提交问题'}
                            </button>
                        </div>

                        {askError ? <div className="notice error">{askError}</div> : null}

                        <div className="page-grid-2">
                            <div className="card subtle-card">
                                <h3>待关注</h3>
                                <ul className="simple-list">
                                    {followupItems.map((item, index) => (
                                        <li key={`${item}-${index}`}>{item}</li>
                                    ))}
                                </ul>
                            </div>
                            <div className="card subtle-card">
                                <h3>回答</h3>
                                <p className="prose-block">{askData?.answer || '提交问题后，这里会显示回答。'}</p>
                            </div>
                        </div>
                    </section>
                </>
            ) : null}
        </div>
    );
}

export default Insights;
