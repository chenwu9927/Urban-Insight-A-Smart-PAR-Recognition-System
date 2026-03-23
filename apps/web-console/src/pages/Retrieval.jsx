import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api, apiUrl } from '../lib/api';

const CLIP_LEAD_SECONDS = 2;
const CLIP_LENGTH_SECONDS = 5;
const MAX_RENDER_RESULTS = 300;

const modeOptions = [
    { id: 'structured', label: '条件检索' },
    { id: 'nl', label: '自然语言检索' },
    { id: 'image', label: '以图搜人' },
];

const defaultFilters = {
    gender: 'All',
    age_group: 'All',
    upper_color: 'All',
    orientation: 'All',
    camera_location: '',
    start_time: '',
    end_time: '',
    has_backpack: false,
    has_bag: false,
    has_hat: false,
    has_glasses: false,
};

const genderMap = { Male: '男', Female: '女' };
const ageGroupMap = { Child: '儿童', Teen: '青少年', Young: '青年', Adult: '成人', Old: '老年' };
const colorMap = {
    Black: '黑色',
    White: '白色',
    Gray: '灰色',
    Red: '红色',
    Blue: '蓝色',
    Green: '绿色',
    Brown: '棕色',
    Yellow: '黄色',
    Purple: '紫色',
    Pink: '粉色',
    Orange: '橙色',
};
const orientationMap = { Front: '正面', Side: '侧面', Back: '背面' };

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

function formatTime(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
        return '--:--';
    }
    const floored = Math.max(0, Math.floor(seconds));
    const minutes = Math.floor(floored / 60);
    const remaining = floored % 60;
    return `${minutes}:${String(remaining).padStart(2, '0')}`;
}

function buildVideoUrl(filename) {
    return apiUrl(`/uploads/${encodeURIComponent(filename)}`);
}

function getResultKey(item, index = 0) {
    return (
        item?.snippet_info?.event_id ||
        `${item?.file_id || 'f'}-${item?.record_id || 'r'}-${item?.snippet_info?.person_id || item?.snippet_info?.pedestrian_id || index}`
    );
}

function renderAccessoryChips(attributes) {
    const chips = [];
    if (attributes?.has_backpack) {
        chips.push('背包');
    }
    if (attributes?.has_bag) {
        chips.push('手提包');
    }
    if (attributes?.has_hat) {
        chips.push('帽子');
    }
    if (attributes?.has_glasses) {
        chips.push('眼镜');
    }
    return chips;
}

function translateAttribute(value, mapping) {
    return mapping[value] || value || '--';
}

function Retrieval() {
    const location = useLocation();
    const navigate = useNavigate();
    const clipRef = useRef(null);
    const videoRef = useRef(null);

    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(location.state?.fileId || '');
    const [mode, setMode] = useState('structured');
    const [filters, setFilters] = useState(defaultFilters);
    const [nlQuery, setNlQuery] = useState('');
    const [useLLM, setUseLLM] = useState(true);
    const [imageQueryFile, setImageQueryFile] = useState(null);
    const [imagePreviewUrl, setImagePreviewUrl] = useState('');
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [searched, setSearched] = useState(false);
    const [activeClip, setActiveClip] = useState(null);
    const [nlMeta, setNlMeta] = useState(null);
    const [imageMeta, setImageMeta] = useState(null);
    const [pageError, setPageError] = useState('');

    const displayResults = useMemo(() => {
        const bestByPerson = new Map();
        const noPerson = [];

        const getTimestamp = (item) => {
            const ts = item?.snippet_info?.timestamp;
            const num = Number(ts);
            return Number.isFinite(num) ? num : Number.POSITIVE_INFINITY;
        };

        for (const item of results || []) {
            const fileId = item?.file_id ?? 'unknown';
            const personId = item?.snippet_info?.person_id || item?.snippet_info?.pedestrian_id;
            if (!personId) {
                noPerson.push(item);
                continue;
            }

            const key = `${fileId}:${personId}`;
            const prev = bestByPerson.get(key);
            if (!prev || getTimestamp(item) < getTimestamp(prev)) {
                bestByPerson.set(key, item);
            }
        }

        return [...bestByPerson.values(), ...noPerson].slice(0, MAX_RENDER_RESULTS);
    }, [results]);

    const hiddenCount = Math.max(0, (results?.length || 0) - displayResults.length);
    const selectedFileMeta = files.find((file) => String(file.id) === String(selectedFile));
    const isSearchDisabled = loading || (mode === 'image' && !imageQueryFile) || (mode === 'nl' && !nlQuery.trim());

    useEffect(() => {
        const loadFiles = async () => {
            try {
                const response = await api.get('/files');
                setFiles((response.data || []).filter((file) => file.status === 'analyzed'));
                setPageError('');
            } catch (error) {
                console.error('Failed to fetch analyzed files', error);
                setPageError('已分析文件列表加载失败。');
            }
        };

        void loadFiles();
    }, []);

    useEffect(() => {
        if (activeClip) {
            clipRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, [activeClip]);

    useEffect(() => {
        if (!imageQueryFile) {
            setImagePreviewUrl('');
            return;
        }
        const objectUrl = URL.createObjectURL(imageQueryFile);
        setImagePreviewUrl(objectUrl);
        return () => URL.revokeObjectURL(objectUrl);
    }, [imageQueryFile]);

    const handleImageQueryFileChange = (event) => {
        const file = event.target.files?.[0] || null;
        setImageQueryFile(file);
    };

    const openClip = (item) => {
        if (!item?.is_video || item?.snippet_info?.timestamp === undefined) {
            return;
        }
        const timestamp = Number(item.snippet_info.timestamp) || 0;
        const duration = item.duration ? Number(item.duration) : null;
        const clipStart = Math.max(0, timestamp - CLIP_LEAD_SECONDS);
        const proposedEnd = clipStart + CLIP_LENGTH_SECONDS;
        const clipEnd = duration ? Math.min(duration, proposedEnd) : proposedEnd;

        setActiveClip({
            key: getResultKey(item),
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

    const replayClip = () => {
        if (!videoRef.current || !activeClip) {
            return;
        }
        videoRef.current.currentTime = activeClip.clipStart;
        videoRef.current.play().catch(() => {});
    };

    const handleClipReady = () => {
        if (!videoRef.current || !activeClip) {
            return;
        }
        const duration = videoRef.current.duration || activeClip.duration || 0;
        const safeStart = Math.min(activeClip.clipStart, duration || activeClip.clipStart);
        videoRef.current.currentTime = safeStart;
        videoRef.current.play().catch(() => {});
    };

    const handleClipTimeUpdate = () => {
        if (!videoRef.current || !activeClip) {
            return;
        }
        if (videoRef.current.currentTime >= activeClip.clipEnd) {
            videoRef.current.pause();
        }
    };

    const resetSearch = () => {
        setFilters(defaultFilters);
        setNlQuery('');
        setUseLLM(true);
        setImageQueryFile(null);
        setImageMeta(null);
        setNlMeta(null);
        setResults([]);
        setSearched(false);
        setActiveClip(null);
        setPageError('');
    };

    const handleSearch = async () => {
        if (mode === 'nl' && !nlQuery.trim()) {
            setPageError('请先输入自然语言描述。');
            return;
        }

        setLoading(true);
        setSearched(true);
        setActiveClip(null);
        setPageError('');
        try {
            setNlMeta(null);
            setImageMeta(null);

            if (mode === 'nl') {
                const payload = {
                    query: nlQuery,
                    file_id: selectedFile ? Number(selectedFile) : null,
                    use_llm: useLLM ? 1 : 0,
                    cache: 1,
                    dedup_person: 1,
                    max_results: MAX_RENDER_RESULTS,
                };
                const response = await api.post('/search/nl', payload);
                setNlMeta({
                    llm_used: response.data.llm_used,
                    cached: response.data.cached,
                    criteria: response.data.criteria,
                    explanation: response.data.explanation,
                });
                setResults(response.data.results || []);
                return;
            }

            if (mode === 'image') {
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
                setImageMeta({ query_attributes: response.data?.query_attributes || {} });
                setResults(response.data?.results || []);
                return;
            }

            const payload = {
                ...filters,
                file_id: selectedFile ? Number(selectedFile) : null,
                dedup_person: true,
                max_results: MAX_RENDER_RESULTS,
            };
            if (!filters.has_backpack) delete payload.has_backpack;
            if (!filters.has_bag) delete payload.has_bag;
            if (!filters.has_hat) delete payload.has_hat;
            if (!filters.has_glasses) delete payload.has_glasses;
            const response = await api.post('/search', payload);
            setResults(response.data || []);
        } catch (error) {
            console.error('Search failed', error);
            setPageError(error?.response?.data?.detail || '检索失败。');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="page-shell">
            <section className="page-header">
                <div className="page-title-group">
                    <span>检索</span>
                    <h1>目标检索</h1>
                    <p>支持条件检索、自然语言检索和以图搜人三种方式。</p>
                </div>
                <div className="page-header-actions">
                    <button type="button" className="btn-primary" onClick={handleSearch} disabled={isSearchDisabled}>
                        {loading ? '检索中...' : '开始检索'}
                    </button>
                    <button type="button" className="btn-secondary" onClick={resetSearch}>
                        重置
                    </button>
                </div>
            </section>

            {pageError ? <div className="notice error">{pageError}</div> : null}

            {!files.length ? (
                <section className="card">
                    <div className="empty-state">
                        还没有可检索的已分析文件。请先到文件库上传并完成分析。
                    </div>
                    <div className="action-row">
                        <button type="button" className="btn-primary" onClick={() => navigate('/files')}>
                            打开文件库
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

                        <div className="field-grid three">
                            <label className="field">
                                <span>文件范围</span>
                                <select value={selectedFile} onChange={(event) => setSelectedFile(event.target.value)}>
                                    <option value="">全部已分析文件</option>
                                    {files.map((file) => (
                                        <option key={file.id} value={file.id}>
                                            {file.filename}
                                        </option>
                                    ))}
                                </select>
                            </label>

                            <div className="field">
                                <span>当前范围</span>
                                <div className="field-readonly">
                                    {selectedFileMeta
                                        ? `${selectedFileMeta.filename}，上传于 ${formatDateTime(selectedFileMeta.upload_time)}`
                                        : '当前将在全部已分析文件中检索'}
                                </div>
                            </div>
                        </div>

                        {mode === 'structured' ? (
                            <>
                                <div className="field-grid three">
                                    <label className="field">
                                        <span>性别</span>
                                        <select
                                            value={filters.gender}
                                            onChange={(event) => setFilters((current) => ({ ...current, gender: event.target.value }))}
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
                                            onChange={(event) => setFilters((current) => ({ ...current, age_group: event.target.value }))}
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
                                            onChange={(event) => setFilters((current) => ({ ...current, upper_color: event.target.value }))}
                                        >
                                            <option value="All">不限</option>
                                            {Object.entries(colorMap).map(([key, label]) => (
                                                <option key={key} value={key}>
                                                    {label}
                                                </option>
                                            ))}
                                        </select>
                                    </label>
                                    <label className="field">
                                        <span>朝向</span>
                                        <select
                                            value={filters.orientation}
                                            onChange={(event) => setFilters((current) => ({ ...current, orientation: event.target.value }))}
                                        >
                                            <option value="All">不限</option>
                                            <option value="Front">正面</option>
                                            <option value="Side">侧面</option>
                                            <option value="Back">背面</option>
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
                                            placeholder="例如 摄像头 01"
                                        />
                                    </label>
                                    <label className="field">
                                        <span>开始时间</span>
                                        <input
                                            type="time"
                                            value={filters.start_time}
                                            onChange={(event) => setFilters((current) => ({ ...current, start_time: event.target.value }))}
                                        />
                                    </label>
                                    <label className="field">
                                        <span>结束时间</span>
                                        <input
                                            type="time"
                                            value={filters.end_time}
                                            onChange={(event) => setFilters((current) => ({ ...current, end_time: event.target.value }))}
                                        />
                                    </label>
                                </div>

                                <div className="action-row wrap">
                                    {[
                                        { key: 'has_backpack', label: '背包' },
                                        { key: 'has_bag', label: '手提包' },
                                        { key: 'has_hat', label: '帽子' },
                                        { key: 'has_glasses', label: '眼镜' },
                                    ].map((item) => (
                                        <button
                                            key={item.key}
                                            type="button"
                                            className={`filter-chip ${filters[item.key] ? 'active' : ''}`}
                                            onClick={() =>
                                                setFilters((current) => ({ ...current, [item.key]: !current[item.key] }))
                                            }
                                        >
                                            {item.label}
                                        </button>
                                    ))}
                                </div>
                            </>
                        ) : null}

                        {mode === 'nl' ? (
                            <div className="field-grid one">
                                <label className="field">
                                    <span>自然语言描述</span>
                                    <textarea
                                        value={nlQuery}
                                        onChange={(event) => setNlQuery(event.target.value)}
                                        placeholder="例如：查找下午两点左右在 Camera 01 附近出现、穿黑色上衣并背双肩包的成年男性。"
                                    />
                                </label>
                                <label className="checkbox-field">
                                    <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                                    <span>优先使用模型解析描述</span>
                                </label>
                            </div>
                        ) : null}

                        {mode === 'image' ? (
                            <div className="field-grid two">
                                <label className="field">
                                    <span>参考图片</span>
                                    <input type="file" accept="image/*" onChange={handleImageQueryFileChange} />
                                </label>
                                <div className="image-preview-card">
                                    {imagePreviewUrl ? <img src={imagePreviewUrl} alt="参考图片" /> : <div className="empty-state compact">请上传参考图片</div>}
                                    {imageQueryFile ? <p>{imageQueryFile.name}</p> : null}
                                </div>
                            </div>
                        ) : null}

                        {mode === 'nl' && nlMeta ? (
                            <div className="notice info">
                                {nlMeta.llm_used ? '模型解析' : '规则解析'}：{nlMeta.explanation || '系统已根据描述转换为检索条件。'}
                            </div>
                        ) : null}

                        {mode === 'image' && imageMeta ? (
                            <div className="notice info">
                                已提取参考图像特征：{JSON.stringify(imageMeta.query_attributes || {})}
                            </div>
                        ) : null}
                    </section>

                    {activeClip ? (
                        <section ref={clipRef} className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">片段回看</h2>
                                    <p className="card-subtitle">
                                        {activeClip.filename} / {activeClip.cameraLocation || '未知摄像头'} / {activeClip.realTime || '--'}
                                    </p>
                                </div>
                                <button type="button" className="btn-secondary" onClick={() => setActiveClip(null)}>
                                    关闭
                                </button>
                            </div>

                            <video
                                key={`${activeClip.videoUrl}-${activeClip.clipStart}`}
                                ref={videoRef}
                                src={activeClip.videoUrl}
                                controls
                                preload="metadata"
                                onLoadedMetadata={handleClipReady}
                                onTimeUpdate={handleClipTimeUpdate}
                                className="clip-player"
                            />

                            <div className="action-row">
                                <span>
                                    片段区间 {formatTime(activeClip.clipStart)} - {formatTime(activeClip.clipEnd)}，目标时间点 {formatTime(activeClip.timestamp)}
                                </span>
                                <button type="button" className="btn-primary" onClick={replayClip}>
                                    重播
                                </button>
                            </div>
                        </section>
                    ) : null}

                    {searched ? (
                        <section className="card">
                            <div className="card-header">
                                <div>
                                    <h2 className="card-title">检索结果</h2>
                                    <p className="card-subtitle">
                                        共显示 {displayResults.length} 条结果
                                        {hiddenCount ? `，另有 ${hiddenCount} 条重复候选已折叠` : ''}
                                    </p>
                                </div>
                            </div>

                            <div className="result-grid">
                                {displayResults.length ? (
                                    displayResults.map((item, index) => {
                                        const attributes = item?.snippet_info?.attributes || {};
                                        const accessoryChips = renderAccessoryChips(attributes);
                                        const itemKey = getResultKey(item, index);
                                        const canPlay = item.is_video && item.snippet_info?.timestamp !== undefined;
                                        const matchScore = item?.snippet_info?.match_score;

                                        return (
                                            <article key={itemKey} className="result-card">
                                                <div className="result-preview">
                                                    {item?.snippet_info?.thumbnail ? (
                                                        <img
                                                            src={apiUrl(`/thumbnails/${item.snippet_info.thumbnail}`)}
                                                            alt="检索结果缩略图"
                                                            loading="lazy"
                                                        />
                                                    ) : (
                                                        <div className="empty-state compact">暂无缩略图</div>
                                                    )}
                                                </div>

                                                <div className="result-body">
                                                    <h3>{item.camera_location || '未知摄像头'}</h3>
                                                    <p>{item.filename}</p>
                                                    <div className="result-meta">
                                                        {item.real_time ? <span>{item.real_time}</span> : null}
                                                        {item.snippet_info?.timestamp !== undefined ? (
                                                            <span>视频时间 {formatTime(item.snippet_info.timestamp)}</span>
                                                        ) : null}
                                                    </div>

                                                    <div className="chip-row">
                                                        {attributes.gender ? <span className="status-tag is-info">{translateAttribute(attributes.gender, genderMap)}</span> : null}
                                                        {attributes.age_group ? <span className="status-tag is-info">{translateAttribute(attributes.age_group, ageGroupMap)}</span> : null}
                                                        {attributes.upper_color ? <span className="status-tag is-warning">{translateAttribute(attributes.upper_color, colorMap)}</span> : null}
                                                        {attributes.orientation ? <span className="status-tag is-warning">{translateAttribute(attributes.orientation, orientationMap)}</span> : null}
                                                        {item?.snippet_info?.person_id ? <span className="status-tag is-info">{item.snippet_info.person_id}</span> : null}
                                                        {typeof matchScore === 'number' ? <span className="status-tag is-success">相似度 {Math.round(matchScore * 100)}%</span> : null}
                                                    </div>

                                                    {accessoryChips.length ? (
                                                        <div className="chip-row">
                                                            {accessoryChips.map((chip) => (
                                                                <span key={chip} className="status-tag is-warning">
                                                                    {chip}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    ) : null}

                                                    <div className="table-actions">
                                                        <button
                                                            type="button"
                                                            className="btn-ghost"
                                                            onClick={() => navigate('/traffic', { state: { fileId: item.file_id } })}
                                                        >
                                                            客流分析
                                                        </button>
                                                        <button
                                                            type="button"
                                                            className="btn-ghost"
                                                            onClick={() => openClip(item)}
                                                            disabled={!canPlay}
                                                        >
                                                            {canPlay ? '查看片段' : '静态图片'}
                                                        </button>
                                                    </div>
                                                </div>
                                            </article>
                                        );
                                    })
                                ) : (
                                    <div className="empty-state">没有找到匹配结果。可以尝试放宽条件或切换检索模式。</div>
                                )}
                            </div>
                        </section>
                    ) : null}
                </>
            ) : null}
        </div>
    );
}

export default Retrieval;
