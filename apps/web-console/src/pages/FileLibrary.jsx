import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { formatDateTime } from '../lib/time';

const ACTIVE_TASK_STATUSES = new Set(['queued', 'running']);

const emptyUploadState = {
    file: null,
    startTime: '',
    autoAnalyze: true,
    pipeline: 'classic_cv',
};

function formatBytes(value) {
    const size = Number(value);
    if (!Number.isFinite(size) || size <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const exponent = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
    const normalized = size / 1024 ** exponent;
    return `${normalized.toFixed(normalized >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function toLocalInputValue(date) {
    const current = date instanceof Date ? date : new Date();
    return new Date(current.getTime() - current.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function getTaskLabel(status) {
    const mapping = {
        queued: '排队中',
        running: '分析中',
        completed: '已完成',
        failed: '失败',
    };
    return mapping[status] || status || '--';
}

function getFileTypeLabel(value) {
    const mapping = {
        image: '图片',
        video: '视频',
    };
    return mapping[value] || value || '--';
}

function getPipelineLabel(value) {
    const mapping = {
        classic_cv: '结构化识别',
        semantic_vlm: '语义研判',
        dual: '双工作流',
    };
    return mapping[value] || value || '--';
}

function getFileStatus(file, task) {
    if (task && ACTIVE_TASK_STATUSES.has(task.status)) {
        return task.status === 'queued' ? '排队中' : '分析中';
    }
    if (file.status === 'analyzed') return '已分析';
    if (file.status === 'error') return '失败';
    return '待分析';
}

function FileLibrary() {
    const navigate = useNavigate();
    const fileInputRef = useRef(null);
    const [files, setFiles] = useState([]);
    const [analysisTasks, setAnalysisTasks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [actionFileId, setActionFileId] = useState(null);
    const [uploadDraft, setUploadDraft] = useState(emptyUploadState);
    const [libraryError, setLibraryError] = useState('');
    const [libraryNotice, setLibraryNotice] = useState('');

    const hasActiveTasks = analysisTasks.some((task) => ACTIVE_TASK_STATUSES.has(task.status));

    const loadLibrary = async ({ silent = false } = {}) => {
        if (!silent) setLoading(true);
        try {
            const [filesResponse, tasksResponse] = await Promise.all([
                api.get('/files'),
                api.get('/analyze/tasks', { params: { limit: 20 } }),
            ]);
            setFiles(filesResponse.data || []);
            setAnalysisTasks(tasksResponse.data || []);
            setLibraryError('');
        } catch (error) {
            console.error('Failed to load file library', error);
            setLibraryError('任务中心加载失败。');
        } finally {
            if (!silent) setLoading(false);
        }
    };

    useEffect(() => {
        void loadLibrary();
    }, []);

    useEffect(() => {
        const timer = window.setInterval(() => {
            void loadLibrary({ silent: true });
        }, hasActiveTasks ? 3000 : 15000);
        return () => window.clearInterval(timer);
    }, [hasActiveTasks]);

    const taskMap = useMemo(() => {
        const map = new Map();
        for (const task of analysisTasks) {
            if (!map.has(task.file_id)) {
                map.set(task.file_id, task);
            }
        }
        return map;
    }, [analysisTasks]);

    const recentTasks = analysisTasks.slice(0, 6);

    const handleChooseFile = () => {
        fileInputRef.current?.click();
    };

    const handleFilePicked = (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        const isVideo = file.type?.startsWith('video/');
        setUploadDraft({
            file,
            startTime: isVideo ? toLocalInputValue(new Date()) : '',
            autoAnalyze: true,
            pipeline: isVideo ? 'dual' : 'classic_cv',
        });
        setLibraryNotice('');
        setLibraryError('');
    };

    const handleUpload = async () => {
        if (!uploadDraft.file || uploading) return;
        setUploading(true);
        setLibraryError('');
        setLibraryNotice('');
        try {
            const formData = new FormData();
            formData.append('file', uploadDraft.file);
            if (uploadDraft.startTime) {
                formData.append('start_time', uploadDraft.startTime);
            }
            const uploadResponse = await api.post('/files/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            const createdFile = uploadResponse.data;

            if (uploadDraft.autoAnalyze && createdFile?.id) {
                await api.post(`/analyze/${createdFile.id}`, null, {
                    params: { immediate: 1, pipeline: uploadDraft.pipeline },
                });
            }

            setUploadDraft(emptyUploadState);
            if (fileInputRef.current) fileInputRef.current.value = '';
            setLibraryNotice(`${createdFile?.filename || '文件'}上传成功。`);
            await loadLibrary();
        } catch (error) {
            console.error('Failed to upload file', error);
            setLibraryError(error?.response?.data?.detail || '上传失败。');
        } finally {
            setUploading(false);
        }
    };

    const handleAnalyze = async (file) => {
        if (!file || actionFileId === file.id) return;
        setActionFileId(file.id);
        setLibraryError('');
        try {
            const selectedPipeline = file.file_type === 'video' ? 'dual' : 'classic_cv';
            await api.post(`/analyze/${file.id}`, null, {
                params: { immediate: 1, pipeline: selectedPipeline },
            });
            await loadLibrary();
        } catch (error) {
            console.error('Failed to start analysis', error);
            setLibraryError(error?.response?.data?.detail || '发起分析失败。');
        } finally {
            setActionFileId(null);
        }
    };

    return (
        <div className="page-shell">
            <input
                ref={fileInputRef}
                type="file"
                accept="image/*,video/*"
                style={{ display: 'none' }}
                onChange={handleFilePicked}
            />

            <section className="card subtle-card">
                <div className="card-title-row">
                    <div>
                        <div className="list-row-title">上传任务</div>
                        <div className="list-row-subtitle">上传图片或视频，并决定是否立即开始分析。</div>
                    </div>
                    <button type="button" className="btn-primary" onClick={handleChooseFile} disabled={uploading}>
                        选择文件
                    </button>
                </div>

                {uploadDraft.file ? (
                    <div className="form-grid compact-form-grid" style={{ marginTop: 16 }}>
                        <div className="form-field">
                            <label>文件</label>
                            <div className="input-like">{uploadDraft.file.name}</div>
                        </div>
                        <div className="form-field">
                            <label>工作流</label>
                            <select
                                value={uploadDraft.pipeline}
                                onChange={(event) =>
                                    setUploadDraft((current) => ({ ...current, pipeline: event.target.value }))
                                }
                            >
                                <option value="classic_cv">结构化识别</option>
                                <option value="semantic_vlm">语义研判</option>
                                <option value="dual">双工作流</option>
                            </select>
                        </div>
                        {uploadDraft.file.type?.startsWith('video/') ? (
                            <div className="form-field">
                                <label>视频开始时间</label>
                                <input
                                    type="datetime-local"
                                    value={uploadDraft.startTime}
                                    onChange={(event) =>
                                        setUploadDraft((current) => ({ ...current, startTime: event.target.value }))
                                    }
                                />
                            </div>
                        ) : null}
                        <label className="checkbox-row">
                            <input
                                type="checkbox"
                                checked={uploadDraft.autoAnalyze}
                                onChange={(event) =>
                                    setUploadDraft((current) => ({ ...current, autoAnalyze: event.target.checked }))
                                }
                            />
                            <span>上传后立即分析</span>
                        </label>
                        <div className="action-row">
                            <button type="button" className="btn-primary" onClick={handleUpload} disabled={uploading}>
                                {uploading ? '上传中…' : '开始上传'}
                            </button>
                            <button type="button" className="btn-ghost" onClick={() => setUploadDraft(emptyUploadState)}>
                                取消
                            </button>
                        </div>
                    </div>
                ) : null}

                {libraryError ? <div className="notice error">{libraryError}</div> : null}
                {libraryNotice ? <div className="notice success">{libraryNotice}</div> : null}
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="list-row-title">最近任务</div>
                    <div className="list compact-list" style={{ marginTop: 12 }}>
                        {recentTasks.map((task) => (
                            <div key={task.task_id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{task.filename || `任务 #${task.task_id}`}</div>
                                    <div className="list-row-subtitle">
                                        {getPipelineLabel(task.pipeline)} · {getTaskLabel(task.status)}
                                    </div>
                                </div>
                                <div className="list-row-meta">
                                    <span>{Number.isFinite(task.progress_percent) ? `${task.progress_percent}%` : '--'}</span>
                                    <button
                                        type="button"
                                        className="btn-ghost"
                                        onClick={() => navigate(`/tasks/${task.file_id}`)}
                                    >
                                        查看
                                    </button>
                                </div>
                            </div>
                        ))}
                        {!recentTasks.length ? <div className="empty-state">暂无任务。</div> : null}
                    </div>
                </section>

                <section className="card">
                    <div className="list-row-title">文件列表</div>
                    {loading ? <div className="empty-state">正在加载…</div> : null}
                    {!loading ? (
                        <div className="list compact-list" style={{ marginTop: 12 }}>
                            {files.map((file) => {
                                const task = taskMap.get(file.id);
                                const isBusy = ACTIVE_TASK_STATUSES.has(task?.status);
                                return (
                                    <div key={file.id} className="list-row">
                                        <div className="list-row-main">
                                            <div className="list-row-title">{file.filename}</div>
                                            <div className="list-row-subtitle">
                                                {getFileTypeLabel(file.file_type)} · {formatBytes(file.file_size)} ·{' '}
                                                {formatDateTime(file.upload_time)}
                                            </div>
                                        </div>
                                        <div className="list-row-meta">
                                            <span>{getFileStatus(file, task)}</span>
                                            <button
                                                type="button"
                                                className="btn-ghost"
                                                onClick={() => navigate(`/tasks/${file.id}`)}
                                            >
                                                详情
                                            </button>
                                            {file.status === 'analyzed' ? null : (
                                                <button
                                                    type="button"
                                                    className="btn-ghost"
                                                    onClick={() => handleAnalyze(file)}
                                                    disabled={isBusy || actionFileId === file.id}
                                                >
                                                    {actionFileId === file.id ? '处理中…' : '分析'}
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                            {!files.length ? <div className="empty-state">还没有上传文件。</div> : null}
                        </div>
                    ) : null}
                </section>
            </div>
        </div>
    );
}

export default FileLibrary;
