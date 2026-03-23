import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';

const ACTIVE_TASK_STATUSES = new Set(['queued', 'running']);

const emptyUploadState = {
    file: null,
    startTime: '',
    autoAnalyze: true,
};

function formatDateTime(value) {
    if (!value) {
        return '--';
    }
    try {
        return new Date(value).toLocaleString('zh-CN');
    } catch {
        return value;
    }
}

function formatBytes(value) {
    const size = Number(value);
    if (!Number.isFinite(size) || size <= 0) {
        return '0 B';
    }
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

function getFileStatus(file, task) {
    if (task && ACTIVE_TASK_STATUSES.has(task.status)) {
        return {
            label: task.status === 'queued' ? '排队中' : '分析中',
            detail: task.status === 'queued' ? '等待工作线程领取任务。' : '识别和提取正在进行。',
        };
    }
    if (file.status === 'analyzed') {
        return {
            label: '已分析',
            detail: '可以用于检索和客流分析。',
        };
    }
    if (file.status === 'error') {
        return {
            label: '失败',
            detail: '上一次分析失败，可以重新发起。',
        };
    }
    return {
        label: '已上传',
        detail: '文件已入库，尚未开始分析。',
    };
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
        if (!silent) {
            setLoading(true);
        }

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
            setLibraryError('文件库数据刷新失败。');
        } finally {
            if (!silent) {
                setLoading(false);
            }
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
                const latestTask = analysisTasks.find((task) => task.file_id === file.id);
                return {
                    ...file,
                    activeTask,
                    latestTask,
                };
            }),
        [analysisTasks, files],
    );

    const stats = useMemo(() => {
        const uploaded = files.length;
        const analyzed = files.filter((file) => file.status === 'analyzed').length;
        const waiting = files.filter((file) => file.status === 'uploaded').length;
        const failed = files.filter((file) => file.status === 'error').length;
        return { uploaded, analyzed, waiting, failed };
    }, [files]);

    const resetUploadDraft = () => {
        setUploadDraft(emptyUploadState);
        setShowUploadModal(false);
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const openFilePicker = () => {
        fileInputRef.current?.click();
    };

    const handleFileSelect = (event) => {
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }
        setUploadDraft({
            file,
            startTime: toLocalInputValue(new Date()),
            autoAnalyze: true,
        });
        setShowUploadModal(true);
    };

    const handleUpload = async () => {
        if (!uploadDraft.file) {
            return;
        }

        setUploading(true);
        setLibraryError('');
        setLibraryNotice('');
        setShowUploadModal(false);

        const formData = new FormData();
        formData.append('file', uploadDraft.file);
        if (uploadDraft.startTime) {
            formData.append('start_time', uploadDraft.startTime);
        }

        try {
            const uploadResponse = await api.post('/files/upload', formData);
            const createdFile = uploadResponse.data;

            if (uploadDraft.autoAnalyze && createdFile?.id) {
                await api.post(`/analyze/${createdFile.id}`);
                setLibraryNotice(`${createdFile.filename} 已上传，并已加入分析队列。`);
            } else {
                setLibraryNotice(`${createdFile?.filename || '文件'} 上传成功。`);
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
        setActionFileId(file.id);
        setLibraryError('');
        setLibraryNotice('');
        try {
            await api.post(`/analyze/${file.id}`);
            setLibraryNotice(`${file.filename} 已加入分析队列。`);
            await loadLibrary({ silent: true });
        } catch (error) {
            console.error('Analysis queue failed', error);
            setLibraryError(error?.response?.data?.detail || '发起分析失败。');
        } finally {
            setActionFileId(null);
        }
    };

    const handleDelete = async (file) => {
        if (!window.confirm(`确定删除 ${file.filename} 吗？这会一并删除关联分析记录。`)) {
            return;
        }

        setActionFileId(file.id);
        setLibraryError('');
        setLibraryNotice('');
        try {
            await api.delete(`/files/${file.id}`);
            setLibraryNotice(`${file.filename} 已删除。`);
            await loadLibrary({ silent: true });
        } catch (error) {
            console.error('Delete failed', error);
            setLibraryError(error?.response?.data?.detail || '删除失败。');
        } finally {
            setActionFileId(null);
        }
    };

    return (
        <div className="page-shell">
            <section className="page-header">
                <div className="page-title-group">
                    <span>文件</span>
                    <h1>文件库</h1>
                    <p>上传图片或视频，设置开始时间，并直接发起分析。</p>
                </div>
                <div className="page-header-actions">
                    <button type="button" className="btn-primary" onClick={openFilePicker} disabled={uploading}>
                        {uploading ? '上传中...' : '上传文件'}
                    </button>
                    <button type="button" className="btn-secondary" onClick={() => void loadLibrary()} disabled={loading}>
                        刷新
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

            <section className="stat-grid">
                <div className="stat-card">
                    <span className="stat-label">文件总数</span>
                    <strong className="stat-value">{stats.uploaded}</strong>
                    <p className="stat-hint">当前文件库中所有媒体文件。</p>
                </div>
                <div className="stat-card">
                    <span className="stat-label">待分析</span>
                    <strong className="stat-value">{stats.waiting}</strong>
                    <p className="stat-hint">已上传但还未完成分析。</p>
                </div>
                <div className="stat-card">
                    <span className="stat-label">已分析</span>
                    <strong className="stat-value">{stats.analyzed}</strong>
                    <p className="stat-hint">可以用于检索和客流分析。</p>
                </div>
                <div className="stat-card">
                    <span className="stat-label">失败</span>
                    <strong className="stat-value">{stats.failed}</strong>
                    <p className="stat-hint">需要重新发起分析或检查数据。</p>
                </div>
            </section>

            <section className="card">
                <div className="card-header">
                    <div>
                        <h2 className="card-title">分析队列</h2>
                        <p className="card-subtitle">查看排队中、分析中和最近的任务。</p>
                    </div>
                </div>
                <div className="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>文件</th>
                                <th>状态</th>
                                <th>进度</th>
                                <th>创建时间</th>
                                <th>备注</th>
                            </tr>
                        </thead>
                        <tbody>
                            {analysisTasks.map((task) => (
                                <tr key={task.task_id}>
                                    <td>{task.filename || `文件 #${task.file_id}`}</td>
                                    <td>{getTaskLabel(task.status)}</td>
                                    <td>{Number.isFinite(task.progress_percent) ? `${task.progress_percent}%` : '--'}</td>
                                    <td>{formatDateTime(task.created_at)}</td>
                                    <td>{task.file_status || '--'}</td>
                                </tr>
                            ))}
                            {!analysisTasks.length ? (
                                <tr>
                                    <td colSpan="5">
                                        <div className="empty-state">当前没有分析任务。</div>
                                    </td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="card">
                <div className="card-header">
                    <div>
                        <h2 className="card-title">文件列表</h2>
                        <p className="card-subtitle">管理上传文件，并在需要时跳转到检索或客流分析。</p>
                    </div>
                </div>

                {loading ? <div className="empty-state">正在加载文件库...</div> : null}

                {!loading ? (
                    <div className="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>文件名</th>
                                    <th>类型</th>
                                    <th>大小</th>
                                    <th>状态</th>
                                    <th>开始时间</th>
                                    <th>上传时间</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filesWithTasks.map((file) => {
                                    const presentation = getFileStatus(file, file.activeTask);
                                    const isBusy = actionFileId === file.id;

                                    return (
                                        <tr key={file.id}>
                                            <td>
                                                <div className="table-primary">{file.filename}</div>
                                                <div className="table-secondary">{presentation.detail}</div>
                                            </td>
                                            <td>{getFileTypeLabel(file.file_type)}</td>
                                            <td>{formatBytes(file.file_size)}</td>
                                            <td>
                                                <span className={`status-tag ${
                                                    presentation.label === '已分析'
                                                        ? 'is-success'
                                                        : presentation.label === '失败'
                                                          ? 'is-danger'
                                                          : presentation.label === '已上传'
                                                            ? 'is-warning'
                                                            : 'is-info'
                                                }`}>
                                                    {presentation.label}
                                                </span>
                                            </td>
                                            <td>{formatDateTime(file.start_time)}</td>
                                            <td>{formatDateTime(file.upload_time)}</td>
                                            <td>
                                                <div className="table-actions">
                                                    {file.status === 'analyzed' ? (
                                                        <>
                                                            <button
                                                                type="button"
                                                                className="btn-ghost"
                                                                onClick={() => navigate('/retrieval', { state: { fileId: file.id } })}
                                                            >
                                                                去检索
                                                            </button>
                                                            <button
                                                                type="button"
                                                                className="btn-ghost"
                                                                onClick={() => navigate('/traffic', { state: { fileId: file.id } })}
                                                            >
                                                                客流分析
                                                            </button>
                                                        </>
                                                    ) : (
                                                        <button
                                                            type="button"
                                                            className="btn-ghost"
                                                            onClick={() => handleAnalyze(file)}
                                                            disabled={Boolean(file.activeTask) || isBusy}
                                                        >
                                                            {file.status === 'error' ? '重新分析' : '开始分析'}
                                                        </button>
                                                    )}
                                                    <button
                                                        type="button"
                                                        className="btn-ghost danger"
                                                        onClick={() => handleDelete(file)}
                                                        disabled={isBusy || Boolean(file.activeTask)}
                                                    >
                                                        删除
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                                {!filesWithTasks.length ? (
                                    <tr>
                                        <td colSpan="7">
                                            <div className="empty-state">文件库为空，请先上传文件。</div>
                                        </td>
                                    </tr>
                                ) : null}
                            </tbody>
                        </table>
                    </div>
                ) : null}
            </section>

            {showUploadModal ? (
                <div className="modal-backdrop">
                    <div className="modal">
                        <div className="card-header">
                            <div>
                                <h2 className="card-title">上传文件</h2>
                                <p className="card-subtitle">{uploadDraft.file?.name || '新文件'}</p>
                            </div>
                        </div>

                        <div className="field-grid one">
                            <label className="field">
                                <span>源视频开始时间</span>
                                <input
                                    type="datetime-local"
                                    value={uploadDraft.startTime}
                                    onChange={(event) =>
                                        setUploadDraft((current) => ({ ...current, startTime: event.target.value }))
                                    }
                                />
                            </label>

                            <label className="checkbox-field">
                                <input
                                    type="checkbox"
                                    checked={uploadDraft.autoAnalyze}
                                    onChange={(event) =>
                                        setUploadDraft((current) => ({ ...current, autoAnalyze: event.target.checked }))
                                    }
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
