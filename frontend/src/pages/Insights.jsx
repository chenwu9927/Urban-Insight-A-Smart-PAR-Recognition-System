import { useEffect, useMemo, useState } from 'react';
import { Sparkles, RefreshCw, Calendar, FileText, MessageSquareText } from 'lucide-react';
import { api } from '../lib/api';

const Chip = ({ children }) => (
  <span style={{
    display: 'inline-flex',
    alignItems: 'center',
    padding: '0.2rem 0.6rem',
    borderRadius: '999px',
    background: '#eef2ff',
    color: '#3730a3',
    fontSize: '0.85rem',
    fontWeight: 600
  }}>
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
        const res = await api.get('/files');
        setFiles(res.data.filter(f => f.status === 'analyzed'));
      } catch (err) {
        console.error(err);
      }
    };
    fetchFiles();
  }, []);

  const fetchInsights = async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      params.set('interval', '60');
      params.set('use_llm', useLLM ? '1' : '0');
      params.set('cache', '1');
      if (selectedFile) params.set('file_id', String(selectedFile));
      else params.set('date', selectedDate);

      const res = await api.get(`/insights?${params.toString()}`);
      setData(res.data);
      setAskData(null);
      setAskError('');
    } catch (err) {
      console.error(err);
      setError('获取智能洞察失败，请稍后重试。');
    } finally {
      setLoading(false);
    }
  };

  const ask = async () => {
    const q = (question || '').trim();
    if (!q) return;
    setAskLoading(true);
    setAskError('');
    try {
      const payload = {
        question: q,
        interval: 60,
        use_llm: useLLM ? 1 : 0,
        cache: 1,
      };
      if (selectedFile) payload.file_id = Number(selectedFile);
      else payload.date = selectedDate;

      const res = await api.post('/insights/ask', payload);
      setAskData(res.data);
    } catch (err) {
      console.error(err);
      setAskError('问答失败，请稍后重试。');
    } finally {
      setAskLoading(false);
    }
  };

  useEffect(() => {
    fetchInsights();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Sparkles size={22} color="#2563eb" />
          <h1 style={{ fontSize: '1.8rem', margin: 0 }}>智能洞察</h1>
          {data?.llm_used ? <Chip>LLM</Chip> : <Chip>规则</Chip>}
        </div>
        <button className="btn-primary" onClick={fetchInsights} disabled={loading} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <RefreshCw size={16} />
          刷新
        </button>
      </div>

      <div className="stat-card" style={{ marginBottom: '1.5rem', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', alignItems: 'end' }}>
        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}><FileText size={16} /> 文件范围</span>
          </label>
          <select
            value={selectedFile}
            onChange={(e) => setSelectedFile(e.target.value)}
            style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
          >
            <option value="">按日期汇总（推荐）</option>
            {files.map(f => (
              <option key={f.id} value={f.id}>{f.filename}</option>
            ))}
          </select>
          <p style={{ margin: '0.5rem 0 0', color: '#64748b', fontSize: '0.85rem' }}>
            选择文件后将忽略日期筛选
          </p>
        </div>

        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}><Calendar size={16} /> 日期</span>
          </label>
          <input
            type="date"
            value={selectedDate}
            disabled={!!selectedFile}
            onChange={(e) => setSelectedDate(e.target.value)}
            style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', justifyContent: 'space-between' }}>
          <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', userSelect: 'none' }}>
            <input type="checkbox" checked={useLLM} onChange={(e) => setUseLLM(e.target.checked)} />
            使用LLM生成洞察（未配置Key时自动降级）
          </label>
          <button className="btn-primary" onClick={fetchInsights} disabled={loading} style={{ height: '42px' }}>
            生成
          </button>
        </div>
      </div>

      {error && (
        <div className="stat-card" style={{ border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b', marginBottom: '1.5rem' }}>
          {error}
        </div>
      )}

      {loading && !data && (
        <div className="stat-card" style={{ color: '#94a3b8' }}>生成中...</div>
      )}

      {data && (
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
          <div className="stat-card">
            <h3 style={{ marginTop: 0 }}>摘要</h3>
            <p style={{ margin: 0, lineHeight: 1.7, color: '#0f172a' }}>
              {data.summary || '暂无摘要'}
            </p>
            <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {data.cached ? <Chip>缓存命中</Chip> : null}
            </div>
            {data.derived?.top_periods?.length ? (
              <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {data.derived.top_periods.map((p, idx) => (
                  <Chip key={idx}>{p.time}: {p.count}</Chip>
                ))}
              </div>
            ) : null}
          </div>

          <div className="stat-card">
            <h3 style={{ marginTop: 0 }}>范围</h3>
            <div style={{ color: '#334155', lineHeight: 1.8 }}>
              <div>date: {data.scope?.date || '-'}</div>
              <div>file_id: {data.scope?.file_id ?? '-'}</div>
              <div>interval: {data.scope?.interval ?? '-'}</div>
            </div>
            <h3 style={{ marginTop: '1.5rem' }}>数据概览</h3>
            <div style={{ color: '#334155', lineHeight: 1.8 }}>
              <div>分析次数: {data.stats?.total_analyses ?? '-'}</div>
              <div>识别行人: {data.stats?.total_pedestrians ?? '-'}</div>
              <div>存储占用: {data.stats?.storage_used ?? '-'}</div>
            </div>
          </div>

          <div className="stat-card" style={{ gridColumn: '1/-1' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
              <div>
                <h3 style={{ marginTop: 0 }}>关键发现</h3>
                <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                  {(data.key_findings || []).length ? (data.key_findings || []).map((x, i) => <li key={i}>{x}</li>) : <li>暂无</li>}
                </ul>
              </div>
              <div>
                <h3 style={{ marginTop: 0 }}>建议</h3>
                <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                  {(data.recommendations || []).length ? (data.recommendations || []).map((x, i) => <li key={i}>{x}</li>) : <li>暂无</li>}
                </ul>
              </div>
              <div>
                <h3 style={{ marginTop: 0 }}>异常/风险</h3>
                <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                  {(data.anomalies || []).length ? (data.anomalies || []).map((x, i) => <li key={i}>{x}</li>) : <li>暂无</li>}
                </ul>
              </div>
              <div>
                <h3 style={{ marginTop: 0 }}>进一步问题</h3>
                <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                  {(data.questions || []).length ? (data.questions || []).map((x, i) => <li key={i}>{x}</li>) : <li>暂无</li>}
                </ul>
              </div>
            </div>
          </div>

          <div className="stat-card" style={{ gridColumn: '1/-1' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <MessageSquareText size={18} /> 询问洞察
              </h3>
              {askData?.llm_used ? <Chip>LLM</Chip> : <Chip>规则</Chip>}
            </div>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') ask(); }}
                placeholder="例如：今天的客流峰值时段是什么？性别年龄有什么特点？"
                style={{ flex: 1, padding: '0.7rem 0.8rem', borderRadius: '0.6rem', border: '1px solid #cbd5e1' }}
              />
              <button className="btn-primary" onClick={ask} disabled={askLoading || !question.trim()} style={{ minWidth: '92px' }}>
                {askLoading ? '分析中…' : '提问'}
              </button>
            </div>
            {askError ? (
              <div style={{ marginTop: '0.75rem', color: '#991b1b' }}>{askError}</div>
            ) : null}
            {askData ? (
              <div style={{ marginTop: '1rem', display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
                <div>
                  <div style={{ color: '#334155', fontSize: '0.9rem' }}>问题：{askData.question}</div>
                  <div style={{ marginTop: '0.5rem', color: '#0f172a', lineHeight: 1.8 }}>
                    {askData.answer || '暂无回答'}
                  </div>
                  {askData.cached ? (
                    <div style={{ marginTop: '0.75rem' }}><Chip>缓存命中</Chip></div>
                  ) : null}
                </div>
                <div>
                  <h4 style={{ margin: 0 }}>可追问</h4>
                  <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.2rem', color: '#0f172a', lineHeight: 1.8 }}>
                    {(askData.suggested_next_questions || []).length
                      ? (askData.suggested_next_questions || []).map((x, i) => (
                        <li key={i}>
                          <a
                            href="#"
                            onClick={(e) => { e.preventDefault(); setQuestion(x); }}
                            style={{ color: '#2563eb', textDecoration: 'none' }}
                          >
                            {x}
                          </a>
                        </li>
                      ))
                      : <li>暂无</li>}
                  </ul>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
};

export default Insights;
