import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { formatDateTime } from '../lib/time';

function formatTime(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
        return '--:--';
    }
    const total = Math.max(0, Math.floor(seconds));
    const minutes = Math.floor(total / 60);
    const remain = total % 60;
    return `${minutes}:${String(remain).padStart(2, '0')}`;
}

function getPipelineLabel(value) {
    const mapping = {
        classic_cv: '结构化识别',
        semantic_vlm: '语义研判',
        dual: '双工作流',
    };
    return mapping[value] || value || '--';
}

function getStatusLabel(value) {
    const mapping = {
        queued: '排队中',
        running: '分析中',
        completed: '已完成',
        failed: '失败',
        analyzed: '已分析',
        uploaded: '已上传',
        processing: '处理中',
        error: '失败',
    };
    return mapping[value] || value || '--';
}

function getFileTypeLabel(value) {
    const mapping = {
        image: '图片',
        video: '视频',
    };
    return mapping[value] || value || '--';
}

function translate(value, mapping) {
    return mapping[value] || value || '--';
}

const genderLabels = { Male: '男', Female: '女' };
const ageGroupLabels = {
    Child: '儿童',
    Teen: '青少年',
    Young: '青年',
    Adult: '成人',
    Old: '老年',
};
const colorLabels = {
    Black: '黑色',
    White: '白色',
    Gray: '灰色',
    Red: '红色',
    Blue: '蓝色',
    Green: '绿色',
    Brown: '棕色',
    Yellow: '黄色',
};

const ACTIVE_TASK_STATUSES = new Set(['queued', 'running']);

function getAccessoryTags(attributes) {
    const tags = [];
    if (attributes?.has_backpack) tags.push('背包');
    if (attributes?.has_bag) tags.push('手提包');
    if (attributes?.has_hat) tags.push('帽子');
    if (attributes?.has_glasses) tags.push('眼镜');
    return tags;
}

function getRecordResultCount(record) {
    if (!record) return '--';
    if (Number.isFinite(record.pedestrian_count) && record.pedestrian_count > 0) {
        return record.pedestrian_count;
    }
    if (Array.isArray(record.results) && record.results.length > 0) {
        return record.results.length;
    }
    if (Array.isArray(record.semantic_results) && record.semantic_results.length > 0) {
        return record.semantic_results.length;
    }
    if (Array.isArray(record.window_summaries) && record.window_summaries.length > 0) {
        return record.window_summaries.length;
    }
    return '--';
}

function TaskDetail() {
    const navigate = useNavigate();
    const { fileId } = useParams();
    const [file, setFile] = useState(null);
    const [tasks, setTasks] = useState([]);
    const [record, setRecord] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const loadDetail = useCallback(
        async ({ silent = false } = {}) => {
            if (!silent) setLoading(true);
            setError('');
            try {
                const [filesResponse, tasksResponse] = await Promise.all([
                    api.get('/files'),
                    api.get('/analyze/tasks', { params: { file_id: Number(fileId), limit: 20 } }),
                ]);

                const currentFile = (filesResponse.data || []).find((item) => String(item.id) === String(fileId));
                if (!currentFile) {
                    setError('没有找到这个文件。');
                    setRecord(null);
                    setTasks([]);
                    setFile(null);
                    return;
                }

                const nextTasks = tasksResponse.data || [];
                const latestCompleted = nextTasks.find((item) => item.result_record_id);

                setFile(currentFile);
                setTasks(nextTasks);

                if (latestCompleted?.result_record_id) {
                    const recordResponse = await api.get(`/analysis/records/${latestCompleted.result_record_id}`);
                    setRecord(recordResponse.data || null);
                } else {
                    setRecord(null);
                }
            } catch (loadError) {
                console.error('Failed to load task detail', loadError);
                setError('任务详情加载失败。');
            } finally {
                if (!silent) setLoading(false);
            }
        },
        [fileId],
    );

    useEffect(() => {
        void loadDetail();
    }, [loadDetail]);

    const latestTask = tasks[0] || null;
    const hasActiveTask = ACTIVE_TASK_STATUSES.has(latestTask?.status) || file?.status === 'processing';

    useEffect(() => {
        if (!hasActiveTask) {
            return undefined;
        }
        const timer = window.setInterval(() => {
            void loadDetail({ silent: true });
        }, 3000);
        return () => window.clearInterval(timer);
    }, [hasActiveTask, loadDetail]);

    const summaryItems = [
        { label: '文件', value: getFileTypeLabel(file?.file_type) },
        { label: '状态', value: getStatusLabel(latestTask?.status || file?.status) },
        { label: '工作流', value: getPipelineLabel(latestTask?.pipeline || record?.pipeline) },
        { label: '结果数', value: getRecordResultCount(record) },
    ];

    const structuredResults = useMemo(() => (record?.results || []).slice(0, 6), [record]);
    const semanticWindows = useMemo(() => (record?.window_summaries || []).slice(0, 5), [record]);
    const eventChain = useMemo(
        () => (record?.video_insights?.event_chain || []).slice(0, 4),
        [record],
    );
    const followups = useMemo(
        () => (record?.video_insights?.agent_followups || record?.video_insights?.operator_recommendations || []).slice(0, 4),
        [record],
    );

    const summaryText =
        record?.video_insights?.incident_summary || (record ? '当前结果以结构化识别为主。' : '结果还没有生成。');

    return (
        <div className="page-shell">
            <div className="action-row">
                <button type="button" className="btn-ghost" onClick={() => navigate('/files')}>
                    返回任务中心
                </button>
                {hasActiveTask ? (
                    <button type="button" className="btn-ghost" onClick={() => void loadDetail()} disabled={loading}>
                        {loading ? '刷新中…' : '立即刷新'}
                    </button>
                ) : null}
                {record?.record_id ? (
                    <button type="button" className="btn-ghost" onClick={() => navigate(`/history`, { state: { recordId: record.record_id } })}>
                        查看报告
                    </button>
                ) : null}
            </div>

            {error ? <div className="notice error">{error}</div> : null}
            {loading ? <div className="empty-state">正在加载...</div> : null}

            {!loading && file ? (
                <>
                    <section className="card subtle-card">
                        <div className="card-title-row">
                            <div>
                                <div className="list-row-title">{file.filename}</div>
                                <div className="list-row-subtitle">
                                    上传于 {formatDateTime(file.upload_time)}
                                </div>
                            </div>
                            <div className="compact-summary">
                                {summaryItems.map((item) => (
                                    <div key={item.label} className="compact-metric">
                                        <span>{item.label}</span>
                                        <strong>{item.value}</strong>
                                    </div>
                                ))}
                            </div>
                        </div>
                            <div className="brief-panel" style={{ marginTop: 16 }}>
                                <p>{summaryText}</p>
                                {record?.video_insights?.risk_level ? <span className="page-chip">风险 {record.video_insights.risk_level}</span> : null}
                                {hasActiveTask ? <span className="page-chip">结果生成中，页面会自动刷新</span> : null}
                            </div>
                        </section>

                    <div className="page-grid-2">
                        <section className="card">
                            <div className="list-row-title">任务进度</div>
                            <div className="list compact-list" style={{ marginTop: 12 }}>
                                {tasks.map((task) => (
                                    <div key={task.task_id} className="list-row">
                                        <div className="list-row-main">
                                            <div className="list-row-title">{getPipelineLabel(task.pipeline)}</div>
                                            <div className="list-row-subtitle">
                                                {getStatusLabel(task.status)} · 创建于 {formatDateTime(task.created_at)}
                                            </div>
                                        </div>
                                        <div className="list-row-meta">
                                            <span>{Number.isFinite(task.progress_percent) ? `${task.progress_percent}%` : '--'}</span>
                                            <span>{task.eta_seconds ? formatTime(task.eta_seconds) : '--'}</span>
                                        </div>
                                    </div>
                                ))}
                                {!tasks.length ? <div className="empty-state">还没有分析任务。</div> : null}
                            </div>
                        </section>

                        <section className="card">
                            <div className="list-row-title">后续建议</div>
                            <div className="list compact-list" style={{ marginTop: 12 }}>
                                {followups.map((item, index) => (
                                    <div key={`${item}-${index}`} className="list-row">
                                        <div className="list-row-main">
                                            <div className="list-row-subtitle">{item}</div>
                                        </div>
                                    </div>
                                ))}
                                {!followups.length ? <div className="empty-state">暂无后续建议。</div> : null}
                            </div>
                        </section>
                    </div>

                    <div className="page-grid-2">
                        <section className="card">
                            <div className="list-row-title">结构化结果</div>
                            <div className="list compact-list" style={{ marginTop: 12 }}>
                                {structuredResults.map((item, index) => {
                                    const tags = getAccessoryTags(item.attributes);
                                    return (
                                        <div key={item.id || index} className="list-row">
                                            <div className="list-row-main">
                                                <div className="list-row-title">
                                                    {translate(item.attributes?.gender, genderLabels)} · {translate(item.attributes?.age_group, ageGroupLabels)}
                                                </div>
                                                <div className="list-row-subtitle">
                                                    上衣 {translate(item.attributes?.upper_color, colorLabels)} · 下衣{' '}
                                                    {translate(item.attributes?.lower_color, colorLabels)}
                                                    {tags.length ? ` · ${tags.join(' / ')}` : ''}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                                {!structuredResults.length ? <div className="empty-state">暂无结构化结果。</div> : null}
                            </div>
                        </section>

                        <section className="card">
                            <div className="list-row-title">语义研判</div>
                            <div className="list compact-list" style={{ marginTop: 12 }}>
                                {semanticWindows.map((window, index) => (
                                    <div key={window.window_id || index} className="list-row">
                                        <div className="list-row-main">
                                            <div className="list-row-title">
                                                时间窗 {index + 1} · 峰值 {window?.crowd_change?.peak_people_count ?? '--'}
                                            </div>
                                            <div className="list-row-subtitle">{window.window_summary || '暂无摘要。'}</div>
                                        </div>
                                    </div>
                                ))}
                                {!semanticWindows.length && eventChain.length ? (
                                    eventChain.map((item, index) => (
                                        <div key={`${item}-${index}`} className="list-row">
                                            <div className="list-row-main">
                                                <div className="list-row-subtitle">{item}</div>
                                            </div>
                                        </div>
                                    ))
                                ) : null}
                                {!semanticWindows.length && !eventChain.length ? <div className="empty-state">暂无语义研判结果。</div> : null}
                            </div>
                        </section>
                    </div>
                </>
            ) : null}
        </div>
    );
}

export default TaskDetail;
