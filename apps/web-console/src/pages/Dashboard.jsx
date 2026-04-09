import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { agentApi, api } from '../lib/api';

function Dashboard() {
    const navigate = useNavigate();
    const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
    const [stats, setStats] = useState({
        total_analyses: 0,
        total_pedestrians: 0,
    });
    const [brief, setBrief] = useState(null);
    const [overview, setOverview] = useState(null);
    const [error, setError] = useState('');

    useEffect(() => {
        let active = true;

        const loadPage = async () => {
            try {
                const [statsResponse, briefResponse, nextOverview] = await Promise.all([
                    api.get(`/stats?date=${today}`),
                    api.get(`/insights/brief?date=${today}&use_llm=1&cache=1`),
                    agentApi.overview(),
                ]);
                if (!active) return;
                setStats(statsResponse.data || {});
                setBrief(briefResponse.data || null);
                setOverview(nextOverview || null);
                setError('');
            } catch (loadError) {
                console.error('Failed to load dashboard', loadError);
                if (active) {
                    setError('总览加载失败。');
                }
            }
        };

        void loadPage();
        const timer = window.setInterval(loadPage, 15000);
        return () => {
            active = false;
            window.clearInterval(timer);
        };
    }, [today]);

    const summaryItems = [
        { label: '分析任务', value: stats.total_analyses ?? 0 },
        { label: '识别人次', value: stats.total_pedestrians ?? 0 },
        { label: '活跃任务', value: overview?.counts?.active_runs ?? 0 },
        { label: '待审批', value: overview?.counts?.pending_approvals ?? 0 },
    ];

    const activeRuns = (overview?.active_runs || []).slice(0, 4);

    return (
        <div className="page-shell">
            {error ? <div className="notice error">{error}</div> : null}

            <section className="card subtle-card compact-card">
                <div className="compact-summary">
                    {summaryItems.map((item) => (
                        <div key={item.label} className="compact-metric">
                            <span>{item.label}</span>
                            <strong>{item.value}</strong>
                        </div>
                    ))}
                </div>
                <div className="compact-actions">
                    <button type="button" className="btn-ghost" onClick={() => navigate('/files')}>
                        上传任务
                    </button>
                    <button type="button" className="btn-ghost" onClick={() => navigate('/agent')}>
                        打开智能体
                    </button>
                </div>
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="list-row-title">今日摘要</div>
                    <div className="brief-panel" style={{ marginTop: 10 }}>
                        <p>{brief?.brief || '暂无摘要。'}</p>
                    </div>
                </section>

                <section className="card">
                    <div className="list-row-title">继续工作</div>
                    <div className="list compact-list" style={{ marginTop: 10 }}>
                        {activeRuns.map((run) => (
                            <div key={run.id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{run.session_title || '未命名任务'}</div>
                                    <div className="list-row-subtitle">{run.result_summary || run.trigger_text || '处理中'}</div>
                                </div>
                                <div className="list-row-meta">
                                    <button type="button" className="btn-ghost" onClick={() => navigate('/agent')}>
                                        打开
                                    </button>
                                </div>
                            </div>
                        ))}
                        {!activeRuns.length ? <div className="empty-state">暂无活跃任务。</div> : null}
                    </div>
                </section>
            </div>
        </div>
    );
}

export default Dashboard;
