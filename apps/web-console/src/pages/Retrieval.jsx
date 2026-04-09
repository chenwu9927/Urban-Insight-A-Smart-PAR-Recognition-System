import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api, apiUrl } from '../lib/api';
import { formatDateTime } from '../lib/time';

const CLIP_LEAD_SECONDS = 2;
const CLIP_LENGTH_SECONDS = 5;
const MAX_RENDER_RESULTS = 200;

const modeOptions = [
    { id: 'structured', label: '条件检索' },
    { id: 'nl', label: '语义描述' },
    { id: 'image', label: '以图搜人' },
];

const defaultFilters = {
    gender: 'All',
    age_group: 'All',
    upper_color: 'All',
    orientation: 'All',
    camera_location: '',
    has_backpack: false,
    has_hat: false,
    has_bag: false,
    has_glasses: false,
};

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
const orientationLabels = {
    Front: '正面',
    Side: '侧面',
    Back: '背面',
};

function formatTime(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '--:--';
    const whole = Math.max(0, Math.floor(seconds));
    const minutes = Math.floor(whole / 60);
    const remain = whole % 60;
    return `${minutes}:${String(remain).padStart(2, '0')}`;
}

function buildVideoUrl(filename) {
    return apiUrl(`/uploads/${encodeURIComponent(filename)}`);
}

function translate(value, mapping) {
    return mapping[value] || value || '--';
}

function getAccessoryTags(attributes) {
    const tags = [];
    if (attributes?.has_backpack) tags.push('背包');
    if (attributes?.has_bag) tags.push('手提包');
    if (attributes?.has_hat) tags.push('帽子');
    if (attributes?.has_glasses) tags.push('眼镜');
    return tags;
}

function Retrieval() {
    const location = useLocation();
    const navigate = useNavigate();
    const clipAnchorRef = useRef(null);
    const videoRef = useRef(null);

    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(location.state?.fileId ? String(location.state.fileId) : '');
    const [mode, setMode] = useState('structured');
    const [filters, setFilters] = useState(defaultFilters);
    const [nlQuery, setNlQuery] = useState('');
    const [useLLM, setUseLLM] = useState(true);
    const [imageQueryFile, setImageQueryFile] = useState(null);
    const [imagePreviewUrl, setImagePreviewUrl] = useState('');
    const [results, setResults] = useState([]);
    const [searched, setSearched] = useState(false);
    const [loading, setLoading] = useState(false);
    const [pageError, setPageError] = useState('');
    const [searchNote, setSearchNote] = useState('');
    const [activeClip, setActiveClip] = useState(null);

    const displayResults = useMemo(
        () => (Array.isArray(results) ? results.slice(0, MAX_RENDER_RESULTS) : []),
        [results],
    );

    const isSearchDisabled = loading || (mode === 'nl' && !nlQuery.trim()) || (mode === 'image' && !imageQueryFile);

    useEffect(() => {
        const loadFiles = async () => {
            try {
                const response = await api.get('/files');
                setFiles((response.data || []).filter((item) => item.status === 'analyzed'));
                setPageError('');
            } catch (error) {
                console.error('Failed to fetch analyzed files', error);
                setPageError('分析文件列表加载失败。');
            }
        };

        void loadFiles();
    }, []);

    useEffect(() => {
        if (!imageQueryFile) {
            setImagePreviewUrl('');
            return undefined;
        }
        const url = URL.createObjectURL(imageQueryFile);
        setImagePreviewUrl(url);
        return () => URL.revokeObjectURL(url);
    }, [imageQueryFile]);

    useEffect(() => {
        if (activeClip) {
            clipAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, [activeClip]);

    const openClip = (item) => {
        if (!item?.is_video || item?.snippet_info?.timestamp === undefined) return;

        const timestamp = Number(item.snippet_info.timestamp) || 0;
        const duration = item.duration ? Number(item.duration) : null;
        const clipStart = Math.max(0, timestamp - CLIP_LEAD_SECONDS);
        const proposedEnd = clipStart + CLIP_LENGTH_SECONDS;
        const clipEnd = duration ? Math.min(duration, proposedEnd) : proposedEnd;

        setActiveClip({
            filename: item.filename,
            cameraLocation: item.camera_location,
            realTime: item.real_time,
            timestamp,
            clipStart,
            clipEnd,
            duration,
            videoUrl: buildVideoUrl(item.filename),
        });
    };

    const handleClipReady = () => {
        if (!videoRef.current || !activeClip) return;
        const duration = videoRef.current.duration || activeClip.duration || 0;
        const startAt = Math.min(activeClip.clipStart, duration || activeClip.clipStart);
        videoRef.current.currentTime = startAt;
        videoRef.current.play().catch(() => {});
    };

    const handleClipTimeUpdate = () => {
        if (!videoRef.current || !activeClip) return;
        if (videoRef.current.currentTime >= activeClip.clipEnd) {
            videoRef.current.pause();
        }
    };

    const handleSearch = async () => {
        setLoading(true);
        setSearched(true);
        setPageError('');
        setSearchNote('');
        setActiveClip(null);

        try {
            if (mode === 'structured') {
                const payload = {
                    ...filters,
                    file_id: selectedFile ? Number(selectedFile) : null,
                    dedup_person: true,
                    max_results: MAX_RENDER_RESULTS,
                };

                Object.entries(payload).forEach(([key, value]) => {
                    if (value === '' || value === 'All') delete payload[key];
                });

                if (!filters.has_backpack) delete payload.has_backpack;
                if (!filters.has_hat) delete payload.has_hat;
                if (!filters.has_bag) delete payload.has_bag;
                if (!filters.has_glasses) delete payload.has_glasses;

                const response = await api.post('/search', payload);
                setResults(response.data || []);
                setSearchNote('已完成条件检索。');
                return;
            }

            if (mode === 'nl') {
                const response = await api.post('/search/nl', {
                    query: nlQuery,
                    file_id: selectedFile ? Number(selectedFile) : null,
                    use_llm: useLLM ? 1 : 0,
                    cache: 1,
                    dedup_person: 1,
                    max_results: MAX_RENDER_RESULTS,
                });
                setResults(response.data?.results || []);
                setSearchNote(response.data?.explanation || '已完成语义检索。');
                return;
            }

            const formData = new FormData();
            formData.append('image', imageQueryFile);
            if (selectedFile) {
                formData.append('file_id', String(Number(selectedFile)));
            }
            formData.append('top_k', String(MAX_RENDER_RESULTS));
            formData.append('min_score', '0.20');

            const response = await api.post('/search/by-image', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            setResults(response.data?.results || []);
            setSearchNote('已完成以图搜人。');
        } catch (error) {
            console.error('Search failed', error);
            setPageError(error?.response?.data?.detail || '检索失败。');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="page-shell">
            <section className="page-toolbar">
                <div className="page-header-actions">
                    <button type="button" className="btn-primary" onClick={handleSearch} disabled={isSearchDisabled}>
                        {loading ? '检索中…' : '开始检索'}
                    </button>
                </div>
            </section>

            {pageError ? <div className="notice error">{pageError}</div> : null}

            {!files.length ? (
                <section className="card">
                    <div className="empty-state">暂无可检索结果。</div>
                    <div className="action-row">
                        <button type="button" className="btn-primary" onClick={() => navigate('/files')}>
                            去任务中心
                        </button>
                    </div>
                </section>
            ) : null}

            {files.length ? (
                <>
                    <section className="card">
                        <div className="mode-tabs">
                            {modeOptions.map((item) => (
                                <button
                                    key={item.id}
                                    type="button"
                                    className={`mode-tab ${mode === item.id ? 'active' : ''}`}
                                    onClick={() => setMode(item.id)}
                                >
                                    {item.label}
                                </button>
                            ))}
                        </div>

                        <div className="field-grid one">
                            <label className="field">
                                <span>检索范围</span>
                                <select value={selectedFile} onChange={(event) => setSelectedFile(event.target.value)}>
                                    <option value="">全部已分析文件</option>
                                    {files.map((file) => (
                                        <option key={file.id} value={file.id}>
                                            {file.filename}
                                        </option>
                                    ))}
                                </select>
                            </label>
                        </div>

                        {mode === 'structured' ? (
                            <>
                                <div className="field-grid three">
                                    <label className="field">
                                        <span>性别</span>
                                        <select
                                            value={filters.gender}
                                            onChange={(event) =>
                                                setFilters((current) => ({ ...current, gender: event.target.value }))
                                            }
                                        >
                                            <option value="All">不限</option>
                                            <option value="Male">男</option>
                                            <option value="Female">女</option>
                                        </select>
                                    </label>
                                    <label className="field">
                                        <span>年龄段</span>
                                        <select
                                            value={filters.age_group}
                                            onChange={(event) =>
                                                setFilters((current) => ({ ...current, age_group: event.target.value }))
                                            }
                                        >
                                            <option value="All">不限</option>
                                            <option value="Child">儿童</option>
                                            <option value="Teen">青少年</option>
                                            <option value="Young">青年</option>
                                            <option value="Adult">成人</option>
                                            <option value="Old">老年</option>
                                        </select>
                                    </label>
                                    <label className="field">
                                        <span>上衣颜色</span>
                                        <select
                                            value={filters.upper_color}
                                            onChange={(event) =>
                                                setFilters((current) => ({ ...current, upper_color: event.target.value }))
                                            }
                                        >
                                            <option value="All">不限</option>
                                            {Object.entries(colorLabels).map(([value, label]) => (
                                                <option key={value} value={value}>
                                                    {label}
                                                </option>
                                            ))}
                                        </select>
                                    </label>
                                </div>

                                <div className="field-grid two">
                                    <label className="field">
                                        <span>朝向</span>
                                        <select
                                            value={filters.orientation}
                                            onChange={(event) =>
                                                setFilters((current) => ({ ...current, orientation: event.target.value }))
                                            }
                                        >
                                            <option value="All">不限</option>
                                            {Object.entries(orientationLabels).map(([value, label]) => (
                                                <option key={value} value={value}>
                                                    {label}
                                                </option>
                                            ))}
                                        </select>
                                    </label>
                                    <label className="field">
                                        <span>摄像头位置</span>
                                        <input
                                            type="text"
                                            value={filters.camera_location}
                                            onChange={(event) =>
                                                setFilters((current) => ({ ...current, camera_location: event.target.value }))
                                            }
                                            placeholder="例如 Camera 01"
                                        />
                                    </label>
                                </div>

                                <div className="compact-actions">
                                    {[
                                        ['has_backpack', '背包'],
                                        ['has_bag', '手提包'],
                                        ['has_hat', '帽子'],
                                        ['has_glasses', '眼镜'],
                                    ].map(([key, label]) => (
                                        <button
                                            key={key}
                                            type="button"
                                            className={`filter-chip ${filters[key] ? 'active' : ''}`}
                                            onClick={() =>
                                                setFilters((current) => ({ ...current, [key]: !current[key] }))
                                            }
                                        >
                                            {label}
                                        </button>
                                    ))}
                                </div>
                            </>
                        ) : null}

                        {mode === 'nl' ? (
                            <div className="field-grid one">
                                <label className="field">
                                    <span>语义描述</span>
                                    <textarea
                                        value={nlQuery}
                                        onChange={(event) => setNlQuery(event.target.value)}
                                        placeholder="例如：查找下午两点左右在 Camera 01 附近停留较久、背双肩包的成年人。"
                                    />
                                </label>
                                <label className="checkbox-field">
                                    <input
                                        type="checkbox"
                                        checked={useLLM}
                                        onChange={(event) => setUseLLM(event.target.checked)}
                                    />
                                    <span>优先使用模型理解这段描述</span>
                                </label>
                            </div>
                        ) : null}

                        {mode === 'image' ? (
                            <div className="field-grid two">
                                <label className="field">
                                    <span>参考图像</span>
                                    <input
                                        type="file"
                                        accept="image/*"
                                        onChange={(event) => setImageQueryFile(event.target.files?.[0] || null)}
                                    />
                                </label>
                                <div className="image-preview-card">
                                    {imagePreviewUrl ? (
                                        <img src={imagePreviewUrl} alt="参考图像预览" />
                                    ) : (
                                        <div className="empty-state compact">上传参考图。</div>
                                    )}
                                    {imageQueryFile ? <p>{imageQueryFile.name}</p> : null}
                                </div>
                            </div>
                        ) : null}
                    </section>

                    {activeClip ? (
                        <section ref={clipAnchorRef} className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">片段预览</h2>
                                    <div className="list-row-subtitle">
                                        {activeClip.cameraLocation || '--'} · {activeClip.realTime || formatTime(activeClip.timestamp)}
                                    </div>
                                </div>
                            </div>
                            <video
                                ref={videoRef}
                                className="clip-player"
                                controls
                                src={activeClip.videoUrl}
                                onLoadedMetadata={handleClipReady}
                                onTimeUpdate={handleClipTimeUpdate}
                            />
                        </section>
                    ) : null}

                    <section className="card">
                        <div className="card-header">
                            <div>
                                <h2 className="card-title">检索结果</h2>
                                {searchNote ? <div className="list-row-subtitle">{searchNote}</div> : null}
                            </div>
                            {searched ? (
                                <span className="page-chip">
                                    共 {displayResults.length} 条
                                    {results.length > displayResults.length ? `，仅显示前 ${displayResults.length} 条` : ''}
                                </span>
                            ) : null}
                        </div>

                        {!searched && !displayResults.length ? <div className="empty-state">开始检索。</div> : null}
                        {searched && !displayResults.length && !loading ? <div className="empty-state">没有结果。</div> : null}

                        <div className="list compact-list">
                            {displayResults.map((item, index) => {
                                const attributes = item?.snippet_info?.attributes || {};
                                const tags = getAccessoryTags(attributes);
                                return (
                                    <div key={`${item.record_id}-${index}`} className="list-row">
                                        <div className="list-row-main">
                                            <div className="list-row-title">
                                                {translate(attributes.gender, genderLabels)} · {translate(attributes.age_group, ageGroupLabels)} ·{' '}
                                                {translate(attributes.upper_color, colorLabels)}
                                            </div>
                                            <div className="list-row-subtitle">
                                                {item.filename} · {item.camera_location || '--'} · {item.real_time || formatDateTime(item.upload_time)}
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
                                        <div className="list-row-meta">
                                            {item.is_video && item?.snippet_info?.timestamp !== undefined ? (
                                                <button type="button" className="btn-ghost" onClick={() => openClip(item)}>
                                                    看片段
                                                </button>
                                            ) : null}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </section>
                </>
            ) : null}
        </div>
    );
}

export default Retrieval;
