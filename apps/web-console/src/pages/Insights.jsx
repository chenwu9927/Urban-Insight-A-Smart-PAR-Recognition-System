import { useCallback, useEffect, useMemo, useState } from 'react';
import { Calendar, FileText, MessageSquareText, RefreshCw, Sparkles } from 'lucide-react';
import { api } from '../lib/api';

const Chip = ({ children }) => (
    <span
        style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '0.2rem 0.6rem',
            borderRadius: '999px',
            background: '#eef2ff',
            color: '#3730a3',
            fontSize: '0.85rem',
            fontWeight: 600,
        }}
    >
        {children}
    </span>
);

const Insights = () => {
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
                setFiles(response.data.filter((file) => file.status === 'analyzed'));
            } catch (error) {
                console.error('Failed to load analyzed files', error);
            }
        };
        fetchFiles();
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
            setAskData(null);
            setAskError('');
        } catch (error) {
            console.error('Failed to fetch insights', error);
            setError('Failed to load insight summary.');
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
        } catch (error) {
            console.error('Failed to ask insight question', error);
            setAskError('Question answering failed.');
        } finally {
            setAskLoading(false);
        }
    };

    useEffect(() => {
        fetchInsights();
    }, [fetchInsights]);

    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', gap: '1rem', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <Sparkles size={22} color="#2563eb" />
                    <h1 style={{ fontSize: '1.8rem', margin: 0 }}>Insights</h1>
                    {data?.llm_used ? <Chip>LLM</Chip> : <Chip>Rule-based</Chip>}
                </div>
                <button className="btn-primary" onClick={fetchInsights} disabled={loading} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <RefreshCw size={16} />
                    Refresh
                </button>
            </div>

            <div className="stat-card" style={{ marginBottom: '1.5rem', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', alignItems: 'end' }}>
                <div>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                            <FileText size={16} />
                            Scope file
                        </span>
                    </label>
                    <select
                        value={selectedFile}
                        onChange={(event) => setSelectedFile(event.target.value)}
                        style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                    >
                        <option value="">Aggregate by date</option>
                        {files.map((file) => (
                            <option key={file.id} value={file.id}>
                                {file.filename}
                            </option>
                        ))}
                    </select>
                    <p style={{ margin: '0.5rem 0 0', color: '#64748b', fontSize: '0.85rem' }}>
                        Picking a file overrides the date filter.
                    </p>
                </div>

                <div>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                            <Calendar size={16} />
                            Date
                        </span>
                    </label>
                    <input
                        type="date"
                        value={selectedDate}
                        disabled={Boolean(selectedFile)}
                        onChange={(event) => setSelectedDate(event.target.value)}
                        style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                    />
                </div>

                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', justifyContent: 'space-between' }}>
                    <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', userSelect: 'none' }}>
                        <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                        Use LLM
                    </label>
                    <button className="btn-primary" onClick={fetchInsights} disabled={loading} style={{ height: '42px' }}>
                        Generate
                    </button>
                </div>
            </div>

            {error ? (
                <div className="stat-card" style={{ border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b', marginBottom: '1.5rem' }}>
                    {error}
                </div>
            ) : null}

            {loading && !data ? <div className="stat-card" style={{ color: '#94a3b8' }}>Generating insight summary...</div> : null}

            {data ? (
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
                    <div className="stat-card">
                        <h3 style={{ marginTop: 0 }}>Summary</h3>
                        <p style={{ margin: 0, lineHeight: 1.7, color: '#0f172a' }}>{data.summary || 'No summary available.'}</p>
                        <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                            {data.cached ? <Chip>Cached</Chip> : null}
                        </div>
                        {data.derived?.top_periods?.length ? (
                            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                                {data.derived.top_periods.map((period, index) => (
                                    <Chip key={index}>
                                        {period.time}: {period.count}
                                    </Chip>
                                ))}
                            </div>
                        ) : null}
                    </div>

                    <div className="stat-card">
                        <h3 style={{ marginTop: 0 }}>Scope</h3>
                        <div style={{ color: '#334155', lineHeight: 1.8 }}>
                            <div>Date: {data.scope?.date || '-'}</div>
                            <div>File ID: {data.scope?.file_id ?? '-'}</div>
                            <div>Interval: {data.scope?.interval ?? '-'}</div>
                        </div>
                        <h3 style={{ marginTop: '1.5rem' }}>Stats snapshot</h3>
                        <div style={{ color: '#334155', lineHeight: 1.8 }}>
                            <div>Analyses: {data.stats?.total_analyses ?? '-'}</div>
                            <div>Pedestrians: {data.stats?.total_pedestrians ?? '-'}</div>
                            <div>Storage used: {data.stats?.storage_used ?? '-'}</div>
                        </div>
                    </div>

                    <div className="stat-card" style={{ gridColumn: '1 / -1' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                            <div>
                                <h3 style={{ marginTop: 0 }}>Key findings</h3>
                                <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                                    {(data.key_findings || []).length
                                        ? data.key_findings.map((item, index) => <li key={index}>{item}</li>)
                                        : <li>No findings available.</li>}
                                </ul>
                            </div>
                            <div>
                                <h3 style={{ marginTop: 0 }}>Recommendations</h3>
                                <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                                    {(data.recommendations || []).length
                                        ? data.recommendations.map((item, index) => <li key={index}>{item}</li>)
                                        : <li>No recommendations available.</li>}
                                </ul>
                            </div>
                            <div>
                                <h3 style={{ marginTop: 0 }}>Anomalies</h3>
                                <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                                    {(data.anomalies || []).length
                                        ? data.anomalies.map((item, index) => <li key={index}>{item}</li>)
                                        : <li>No anomalies detected.</li>}
                                </ul>
                            </div>
                            <div>
                                <h3 style={{ marginTop: 0 }}>Open questions</h3>
                                <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                                    {(data.questions || []).length
                                        ? data.questions.map((item, index) => <li key={index}>{item}</li>)
                                        : <li>No follow-up questions.</li>}
                                </ul>
                            </div>
                        </div>
                    </div>

                    <div className="stat-card" style={{ gridColumn: '1 / -1' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', gap: '1rem', flexWrap: 'wrap' }}>
                            <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <MessageSquareText size={18} />
                                Ask the insight engine
                            </h3>
                            {askData?.llm_used ? <Chip>LLM</Chip> : <Chip>Rule-based</Chip>}
                        </div>
                        <div style={{ display: 'flex', gap: '0.75rem' }}>
                            <input
                                value={question}
                                onChange={(event) => setQuestion(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter') {
                                        askQuestion();
                                    }
                                }}
                                placeholder="Example: When was the busiest period and what stands out?"
                                style={{ flex: 1, padding: '0.7rem 0.8rem', borderRadius: '0.6rem', border: '1px solid #cbd5e1' }}
                            />
                            <button className="btn-primary" onClick={askQuestion} disabled={askLoading || !question.trim()} style={{ minWidth: '92px' }}>
                                {askLoading ? 'Thinking...' : 'Ask'}
                            </button>
                        </div>
                        {askError ? <div style={{ marginTop: '0.75rem', color: '#991b1b' }}>{askError}</div> : null}
                        {askData ? (
                            <div style={{ marginTop: '1rem', display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
                                <div>
                                    <div style={{ color: '#334155', fontSize: '0.9rem' }}>Question</div>
                                    <div style={{ marginTop: '0.5rem', color: '#0f172a', lineHeight: 1.8 }}>{askData.answer || 'No answer available.'}</div>
                                    {askData.cached ? (
                                        <div style={{ marginTop: '0.75rem' }}>
                                            <Chip>Cached</Chip>
                                        </div>
                                    ) : null}
                                </div>
                                <div>
                                    <div style={{ color: '#334155', fontSize: '0.9rem' }}>Query</div>
                                    <div style={{ marginTop: '0.5rem', color: '#0f172a', lineHeight: 1.7 }}>{askData.question}</div>
                                </div>
                            </div>
                        ) : null}
                    </div>
                </div>
            ) : null}
        </div>
    );
};

export default Insights;
