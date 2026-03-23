import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';

function Insights() {
    const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
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
            setData(response.data);
        } catch (loadError) {
            console.error('Failed to fetch insights', loadError);
            setError('洞察简报加载失败。');
        } finally {
            setLoading(false);
        }
    }, [selectedDate, selectedFile, useLLM]);

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
            setAskData(response.data);
        } catch (askFailure) {
            console.error('Failed to ask insight question', askFailure);
            setAskError('提问失败。');
        } finally {
            setAskLoading(false);
        }
    };

    useEffect(() => {
        void fetchInsights();
    }, [fetchInsights]);

    return (
        <div className="page-shell">
            <section className="page-header">
                <div className="page-title-group">
                    <span>洞察</span>
                    <h1>洞察简报</h1>
                    <p>按日期或文件生成摘要，并继续追问具体问题。</p>
                </div>
                <div className="page-header-actions">
                    <button type="button" className="btn-primary" onClick={fetchInsights} disabled={loading}>
                        {loading ? '生成中...' : '刷新简报'}
                    </button>
                </div>
            </section>

            <section className="card">
                <div className="field-grid three">
                    <label className="field">
                        <span>文件范围</span>
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
                        <span>使用模型生成内容</span>
                    </label>
                </div>
            </section>

            {error ? <div className="notice error">{error}</div> : null}

            {data ? (
                <>
                    <div className="page-grid-2">
                        <section className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">摘要</h2>
                                    <p className="card-subtitle">{data.llm_used ? '模型生成' : '规则生成'}</p>
                                </div>
                            </div>
                            <p className="prose-block">{data.summary || '暂无摘要内容。'}</p>
                        </section>

                        <section className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">范围信息</h2>
                                    <p className="card-subtitle">当前简报的输入范围。</p>
                                </div>
                            </div>
                            <div className="list">
                                <div className="list-row">
                                    <div className="list-row-main">
                                        <div className="list-row-title">日期</div>
                                    </div>
                                    <div className="list-row-meta">
                                        <span>{data.scope?.date || '--'}</span>
                                    </div>
                                </div>
                                <div className="list-row">
                                    <div className="list-row-main">
                                        <div className="list-row-title">文件 ID</div>
                                    </div>
                                    <div className="list-row-meta">
                                        <span>{data.scope?.file_id ?? '--'}</span>
                                    </div>
                                </div>
                                <div className="list-row">
                                    <div className="list-row-main">
                                        <div className="list-row-title">行人数量</div>
                                    </div>
                                    <div className="list-row-meta">
                                        <span>{data.stats?.total_pedestrians ?? '--'}</span>
                                    </div>
                                </div>
                            </div>
                        </section>
                    </div>

                    <div className="page-grid-2">
                        <section className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">重点发现</h2>
                                </div>
                            </div>
                            <ul className="simple-list">
                                {(data.key_findings || []).length ? (
                                    data.key_findings.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                                ) : (
                                    <li>暂无重点发现。</li>
                                )}
                            </ul>
                        </section>

                        <section className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">建议</h2>
                                </div>
                            </div>
                            <ul className="simple-list">
                                {(data.recommendations || []).length ? (
                                    data.recommendations.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                                ) : (
                                    <li>暂无建议。</li>
                                )}
                            </ul>
                        </section>

                        <section className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">异常</h2>
                                </div>
                            </div>
                            <ul className="simple-list">
                                {(data.anomalies || []).length ? (
                                    data.anomalies.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                                ) : (
                                    <li>暂无异常。</li>
                                )}
                            </ul>
                        </section>

                        <section className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">待追问问题</h2>
                                </div>
                            </div>
                            <ul className="simple-list">
                                {(data.questions || []).length ? (
                                    data.questions.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                                ) : (
                                    <li>暂无待追问问题。</li>
                                )}
                            </ul>
                        </section>
                    </div>

                    <section className="card">
                        <div className="card-header">
                            <div>
                                <h2 className="card-title">继续提问</h2>
                                <p className="card-subtitle">在当前范围内继续追问细节。</p>
                            </div>
                        </div>

                        <div className="field-grid one">
                            <label className="field">
                                <span>问题</span>
                                <textarea
                                    value={question}
                                    onChange={(event) => setQuestion(event.target.value)}
                                    placeholder="例如：最繁忙的时段是什么？有哪些异常值得继续排查？"
                                />
                            </label>
                        </div>

                        <div className="action-row">
                            <button type="button" className="btn-primary" onClick={askQuestion} disabled={askLoading || !question.trim()}>
                                {askLoading ? '处理中...' : '提交问题'}
                            </button>
                        </div>

                        {askError ? <div className="notice error">{askError}</div> : null}

                        {askData ? (
                            <div className="page-grid-2 inner-grid">
                                <div className="card subtle-card">
                                    <h3>回答</h3>
                                    <p className="prose-block">{askData.answer || '暂无回答。'}</p>
                                </div>
                                <div className="card subtle-card">
                                    <h3>问题</h3>
                                    <p className="prose-block">{askData.question}</p>
                                </div>
                            </div>
                        ) : null}
                    </section>
                </>
            ) : null}
        </div>
    );
}

export default Insights;
