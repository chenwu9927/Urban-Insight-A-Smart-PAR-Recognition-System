import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';

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
    const [showUploadModal, setShowUploadModal] = useState(false);
    const [uploadDraft, setUploadDraft] = useState(emptyUploadState);
    const [libraryError, setLibraryError] = useState('');
    const [libraryNotice, setLibraryNotice] = useState('');

    const hasActiveTasks = analysisTasks.some((task) => ACTIVE_TASK_STATUSES.has(task.status));

    const loadLibrary = async ({ silent = false } = {}) => {
        if (!silent) setLoading(true);
        try {
            const [filesResponse, tasksResponse] = await Promise.all([
                api.get('/files'),
                api.get('/analyze/tasks', { params: { limit: 12 } }),
            ]);
            setFiles(filesResponse.data || []);
            setAnalysisTasks(tasksResponse.data || []);
            setLibraryError('');
        } catch (error) {
            console.error('Failed to load library data', error);
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

    const filesWithTasks = useMemo(
        () =>
            files.map((file) => {
                const activeTask = analysisTasks.find(
                    (task) => task.file_id === file.id && ACTIVE_TASK_STATUSES.has(task.status),
                );
                return { ...file, activeTask };
            }),
        [analysisTasks, files],
    );

    const stats = useMemo(() => {
        const uploaded = files.length;
        const analyzed = files.filter((file) => file.status === 'analyzed').length;
        const running = analysisTasks.filter((task) => ACTIVE_TASK_STATUSES.has(task.status)).length;
        return { uploaded, analyzed, running };
    }, [analysisTasks, files]);

    const resetUploadDraft = () => {
        setUploadDraft(emptyUploadState);
        setShowUploadModal(false);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleFileSelect = (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        setUploadDraft({
            file,
            startTime: toLocalInputValue(new Date()),
            autoAnalyze: true,
            pipeline: file.type?.startsWith('video/') ? 'dual' : 'classic_cv',
        });
        setShowUploadModal(true);
    };

    const handleUpload = async () => {
        if (!uploadDraft.file) return;
        setUploading(true);
        setLibraryError('');
        setLibraryNotice('');
        setShowUploadModal(false);

        const formData = new FormData();
        formData.append('file', uploadDraft.file);
        if (uploadDraft.startTime) formData.append('start_time', uploadDraft.startTime);

        try {
            const uploadResponse = await api.post('/files/upload', formData);
            const createdFile = uploadResponse.data;
            if (uploadDraft.autoAnalyze && createdFile?.id) {
                await api.post(`/analyze/${createdFile.id}`, null, {
                    params: { pipeline: uploadDraft.pipeline },
                });
                setLibraryNotice(`${createdFile.filename} 已加入${getPipelineLabel(uploadDraft.pipeline)}。`);
            } else {
                setLibraryNotice(`${createdFile?.filename || '文件'}上传成功。`);
            }
            await loadLibrary({ silent: true });
        } catch (error) {
            console.error('Upload failed', error);
            setLibraryError(error?.response?.data?.detail || '上传失败。');
        } finally {
            setUploading(false);
            resetUploadDraft();
        }
    };

    const handleAnalyze = async (file) => {
        const selectedPipeline = file.file_type === 'video' ? 'dual' : 'classic_cv';
        setActionFileId(file.id);
        setLibraryError('');
        setLibraryNotice('');
        try {
            await api.post(`/analyze/${file.id}`, null, {
                params: { pipeline: selectedPipeline },
            });
            setLibraryNotice(`${file.filename} 已加入${getPipelineLabel(selectedPipeline)}。`);
            await loadLibrary({ silent: true });
        } catch (error) {
            console.error('Analysis queue failed', error);
            setLibraryError(error?.response?.data?.detail || '发起分析失败。');
        } finally {
            setActionFileId(null);
        }
    };

    return (
        <div className="page-shell">
            <section className="page-toolbar">
                <div className="page-header-actions">
                    <button type="button" className="btn-primary" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                        {uploading ? '上传中…' : '上传文件'}
                    </button>
                </div>
            </section>

            <input
                ref={fileInputRef}
                type="file"
                accept="image/*,video/mp4,video/avi,video/x-msvideo"
                style={{ display: 'none' }}
                onChange={handleFileSelect}
            />

            {libraryError ? <div className="notice error">{libraryError}</div> : null}
            {libraryNotice ? <div className="notice success">{libraryNotice}</div> : null}

            <section className="card subtle-card compact-card">
                <div className="compact-summary">
                    <div className="compact-metric">
                        <span>文件</span>
                        <strong>{stats.uploaded}</strong>
                    </div>
                    <div className="compact-metric">
                        <span>分析中</span>
                        <strong>{stats.running}</strong>
                    </div>
                    <div className="compact-metric">
                        <span>已完成</span>
                        <strong>{stats.analyzed}</strong>
                    </div>
                </div>
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="list-row-title">最近任务</div>
                    <div className="list compact-list" style={{ marginTop: 10 }}>
                        {analysisTasks.map((task) => (
                            <div key={task.task_id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{task.filename || `文件 #${task.file_id}`}</div>
                                    <div className="list-row-subtitle">
                                        {getPipelineLabel(task.pipeline)} · {getTaskLabel(task.status)}
                                    </div>
                                </div>
                                <div className="list-row-meta">
                                    <span>{Number.isFinite(task.progress_percent) ? `${task.progress_percent}%` : '--'}</span>
                                    <button type="button" className="btn-ghost" onClick={() => navigate(`/tasks/${task.file_id}`)}>
                                        详情
                                    </button>
                                </div>
                            </div>
                        ))}
                        {!analysisTasks.length ? <div className="empty-state">暂无任务。</div> : null}
                    </div>
                </section>

                <section className="card">
                    <div className="list-row-title">文件</div>
                    {loading ? <div className="empty-state">正在加载…</div> : null}
                    {!loading ? (
                        <div className="list compact-list" style={{ marginTop: 10 }}>
                            {filesWithTasks.map((file) => {
                                const isBusy = actionFileId === file.id;
                                const status = getFileStatus(file, file.activeTask);
                                const taskActionDisabled = Boolean(file.activeTask) || isBusy;
                                return (
                                    <div key={file.id} className="list-row">
                                        <div className="list-row-main">
                                            <div className="list-row-title">{file.filename}</div>
                                            <div className="list-row-subtitle">
                                                {getFileTypeLabel(file.file_type)} · {formatBytes(file.file_size)} · {status}
                                            </div>
                                        </div>
                                        <div className="list-row-meta">
                                            {file.status === 'analyzed' ? (
                                                <button type="button" className="btn-ghost" onClick={() => navigate(`/tasks/${file.id}`)}>
                                                    详情
                                                </button>
                                            ) : (
                                                <button
                                                    type="button"
                                                    className="btn-ghost"
                                                    onClick={() => handleAnalyze(file)}
                                                    disabled={taskActionDisabled}
                                                >
                                                    {file.activeTask ? '处理中' : '开始'}
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                            {!filesWithTasks.length ? <div className="empty-state">暂无文件。</div> : null}
                        </div>
                    ) : null}
                </section>
            </div>

            {showUploadModal ? (
                <div className="modal-backdrop">
                    <div className="modal">
                        <div className="list-row-title">上传文件</div>
                        {uploadDraft.file?.name ? <div className="list-row-subtitle">{uploadDraft.file.name}</div> : null}

                        <div className="field-grid one" style={{ marginTop: 14 }}>
                            <label className="field">
                                <span>开始时间</span>
                                <input
                                    type="datetime-local"
                                    value={uploadDraft.startTime}
                                    onChange={(event) => setUploadDraft((current) => ({ ...current, startTime: event.target.value }))}
                                />
                            </label>

                            <label className="field">
                                <span>分析方式</span>
                                <select
                                    value={uploadDraft.pipeline}
                                    onChange={(event) => setUploadDraft((current) => ({ ...current, pipeline: event.target.value }))}
                                >
                                    <option value="classic_cv">结构化识别</option>
                                    <option value="semantic_vlm" disabled={uploadDraft.file?.type && !uploadDraft.file.type.startsWith('video/')}>
                                        语义研判（视频）
                                    </option>
                                    <option value="dual" disabled={uploadDraft.file?.type && !uploadDraft.file.type.startsWith('video/')}>
                                        双工作流（视频）
                                    </option>
                                </select>
                            </label>

                            <label className="checkbox-field">
                                <input
                                    type="checkbox"
                                    checked={uploadDraft.autoAnalyze}
                                    onChange={(event) => setUploadDraft((current) => ({ ...current, autoAnalyze: event.target.checked }))}
                                />
                                <span>上传后立即分析</span>
                            </label>
                        </div>

                        <div className="modal-actions">
                            <button type="button" className="btn-secondary" onClick={resetUploadDraft}>
                                取消
                            </button>
                            <button type="button" className="btn-primary" onClick={handleUpload}>
                                上传
                            </button>
                        </div>
                    </div>
                </div>
            ) : null}
        </div>
    );
}

export default FileLibrary;
