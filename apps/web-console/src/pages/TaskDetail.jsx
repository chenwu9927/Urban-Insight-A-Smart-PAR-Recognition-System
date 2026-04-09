import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';

function formatDateTime(value) {
    if (!value) return '--';
    try {
        return new Date(value).toLocaleString('zh-CN');
    } catch {
        return value;
    }
}

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

function getAccessoryTags(attributes) {
    const tags = [];
    if (attributes?.has_backpack) tags.push('背包');
    if (attributes?.has_bag) tags.push('手提包');
    if (attributes?.has_hat) tags.push('帽子');
    if (attributes?.has_glasses) tags.push('眼镜');
    return tags;
}

function TaskDetail() {
    const navigate = useNavigate();
    const { fileId } = useParams();
    const [file, setFile] = useState(null);
    const [tasks, setTasks] = useState([]);
    const [record, setRecord] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        const loadDetail = async () => {
            setLoading(true);
            setError('');
            try {
                const [filesResponse, tasksResponse] = await Promise.all([
                    api.get('/files'),
                    api.get('/analyze/tasks', { params: { file_id: Number(fileId), limit: 20 } }),
                ]);

                const currentFile = (filesResponse.data || []).find((item) => String(item.id) === String(fileId));
                if (!currentFile) {
                    setError('没有找到这个文件。');
                    setLoading(false);
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
                setLoading(false);
            }
        };

        void loadDetail();
    }, [fileId]);

    const latestTask = tasks[0] || null;
    const summaryItems = useMemo(
        () => [
            { label: '文件', value: getFileTypeLabel(file?.file_type) },
            { label: '状态', value: getStatusLabel(latestTask?.status || file?.status) },
            { label: '工作流', value: getPipelineLabel(latestTask?.pipeline || record?.pipeline) },
            { label: '结果', value: record?.pedestrian_count ?? record?.semantic_results?.length ?? '--' },
        ],
        [file, latestTask, record],
    );

    const structuredResults = (record?.results || []).slice(0, 6);
    const semanticWindows = (record?.window_summaries || []).slice(0, 5);
    const eventChain = (record?.video_insights?.event_chain || []).slice(0, 4);
    const followups = (record?.video_insights?.agent_followups || record?.video_insights?.operator_recommendations || []).slice(0, 4);
    const conclusion =
        record?.video_insights?.incident_summary ||
        (record ? '当前结果以结构化识别为主。' : '结果还没出来。');

    return (
        <div className="page-shell">
            <section className="page-toolbar">
                <div className="page-header-actions">
                    <button type="button" className="btn-secondary" onClick={() => navigate('/files')}>
                        返回
                    </button>
                    {file?.status === 'analyzed' ? (
                        <button
                            type="button"
                            className="btn-primary"
                            onClick={() => navigate('/retrieval', { state: { fileId: file.id } })}
                        >
                            检索
                        </button>
                    ) : null}
                </div>
            </section>

            {error ? <div className="notice error">{error}</div> : null}
            {loading ? <div className="empty-state">正在加载...</div> : null}

            {!loading && file ? (
                <>
                    <section className="card">
                        <div className="list-row-title">{file.filename}</div>
                        <div className="list-row-subtitle">{formatDateTime(file.upload_time)}</div>

                        <div className="action-row" style={{ marginTop: 10 }}>
                            <span className="page-chip">{summaryItems[1].value}</span>
                            <span className="page-chip">{summaryItems[2].value}</span>
                            {record?.video_insights?.risk_level ? <span className="page-chip">风险 {record.video_insights.risk_level}</span> : null}
                            {record?.duration ? <span className="page-chip">时长 {formatTime(record.duration)}</span> : null}
                        </div>

                        <div className="compact-summary" style={{ marginTop: 12 }}>
                            {summaryItems.map((item) => (
                                <div key={item.label} className="compact-metric">
                                    <span>{item.label}</span>
                                    <strong>{item.value}</strong>
                                </div>
                            ))}
                        </div>

                        <div className="brief-panel">
                            <p className="prose-block">{conclusion}</p>
                        </div>
                    </section>

                    <div className="page-grid-2">
                        <section className="card">
                            <div className="list-row-title">任务</div>
                            <div className="list compact-list" style={{ marginTop: 10 }}>
                                {tasks.map((task) => (
                                    <div key={task.task_id} className="list-row">
                                        <div className="list-row-main">
                                            <div className="list-row-title">{getPipelineLabel(task.pipeline)}</div>
                                            <div className="list-row-subtitle">
                                                {getStatusLabel(task.status)} · {formatDateTime(task.started_at || task.created_at)}
                                            </div>
                                        </div>
                                        <div className="list-row-meta">
                                            <span>{Number.isFinite(task.progress_percent) ? `${task.progress_percent}%` : '--'}</span>
                                        </div>
                                    </div>
                                ))}
                                {!tasks.length ? <div className="empty-state">暂无任务。</div> : null}
                            </div>
                        </section>

                        <section className="card">
                            <div className="list-row-title">结构化</div>
                            <div className="list compact-list" style={{ marginTop: 10 }}>
                                {structuredResults.map((item, index) => {
                                    const attributes = item?.attributes || {};
                                    const tags = getAccessoryTags(attributes);
                                    return (
                                        <div key={`${index}-${item.timestamp || index}`} className="list-row">
                                            <div className="list-row-main">
                                                <div className="list-row-title">
                                                    {translate(attributes.gender, genderLabels)} ·{' '}
                                                    {translate(attributes.age_group, ageGroupLabels)} ·{' '}
                                                    {translate(attributes.upper_color, colorLabels)}
                                                </div>
                                                <div className="list-row-subtitle">
                                                    {file.camera_location || record?.camera_location || '--'} · {formatTime(Number(item.timestamp) || 0)}
                                                </div>
                                                {tags.length ? (
                                                    <div className="chip-row">
                                                        {tags.map((tag) => (
                                                            <span key={tag} className="filter-chip active">
                                                                {tag}
                                                            </span>
                                                        ))}
                                                    </div>
                                                ) : null}
                                            </div>
                                        </div>
                                    );
                                })}
                                {!structuredResults.length ? <div className="empty-state">暂无结果。</div> : null}
                            </div>
                        </section>
                    </div>

                    <section className="card">
                        <div className="list-row-title">语义</div>
                        <div className="list compact-list" style={{ marginTop: 10 }}>
                            {semanticWindows.map((window) => (
                                <div key={`${window.window_start}-${window.window_end}`} className="list-row">
                                    <div className="list-row-main">
                                        <div className="list-row-title">
                                            {formatTime(window.window_start)} - {formatTime(window.window_end)}
                                        </div>
                                        <div className="list-row-subtitle">{window.window_summary}</div>
                                    </div>
                                    <div className="list-row-meta">
                                        <span>峰值 {window?.crowd_change?.peak_people_count ?? '--'}</span>
                                    </div>
                                </div>
                            ))}
                            {!semanticWindows.length ? <div className="empty-state">暂无结果。</div> : null}
                        </div>

                        {eventChain.length || followups.length ? (
                            <div className="page-grid-2 inner-grid">
                                <div className="card subtle-card">
                                    <h3>事件</h3>
                                    <ul className="simple-list">
                                        {eventChain.length ? eventChain.map((item, index) => <li key={`${item}-${index}`}>{item}</li>) : <li>暂无。</li>}
                                    </ul>
                                </div>
                                <div className="card subtle-card">
                                    <h3>后续</h3>
                                    <ul className="simple-list">
                                        {followups.length ? followups.map((item, index) => <li key={`${item}-${index}`}>{item}</li>) : <li>暂无。</li>}
                                    </ul>
                                </div>
                            </div>
                        ) : null}
                    </section>
                </>
            ) : null}
        </div>
    );
}

export default TaskDetail;
