import { useState, useEffect, useRef, useMemo } from 'react';
import { Search, PlayCircle, Sparkles, ImageUp } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { api, apiUrl } from '../lib/api';

const CLIP_LEAD_SECONDS = 2;
const CLIP_LENGTH_SECONDS = 5;
const MAX_RENDER_RESULTS = 300;

const Retrieval = () => {
    const location = useLocation();
    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(location.state?.fileId || '');

    const [filters, setFilters] = useState({
        gender: 'All',
        age_group: 'All',
        upper_color: 'All',
        orientation: 'All',
        has_backpack: false,
        has_bag: false,
        has_hat: false,
        has_glasses: false,
    });
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [searched, setSearched] = useState(false);
    const [activeClip, setActiveClip] = useState(null);
    const clipRef = useRef(null);
    const videoRef = useRef(null);

    const [mode, setMode] = useState('structured'); // structured | nl | image
    const [nlQuery, setNlQuery] = useState('');
    const [useLLM, setUseLLM] = useState(true);
    const [nlMeta, setNlMeta] = useState(null);
    const [imageQueryFile, setImageQueryFile] = useState(null);
    const [imageMeta, setImageMeta] = useState(null);

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

        const merged = [...bestByPerson.values(), ...noPerson];
        return merged.slice(0, MAX_RENDER_RESULTS);
    }, [results]);

    const hiddenCount = Math.max(0, (results?.length || 0) - displayResults.length);

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

    useEffect(() => {
        if (activeClip) {
            clipRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, [activeClip]);

    const formatTime = (seconds) => {
        if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
            return '--:--';
        }
        const floored = Math.max(0, Math.floor(seconds));
        const minutes = Math.floor(floored / 60);
        const remaining = floored % 60;
        return `${minutes}:${String(remaining).padStart(2, '0')}`;
    };

    const buildVideoUrl = (filename) => apiUrl(`/uploads/${encodeURIComponent(filename)}`);

    const getResultKey = (item, index = 0) => {
        return (
            item?.snippet_info?.event_id ||
            `${item?.file_id || 'f'}-${item?.record_id || 'r'}-${item?.snippet_info?.person_id || item?.snippet_info?.pedestrian_id || index}`
        );
    };

    const handleImageQueryFileChange = (e) => {
        const file = e.target.files?.[0] || null;
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
            videoUrl: buildVideoUrl(item.filename)
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

    const handleSearch = async () => {
        setLoading(true);
        setSearched(true);
        setActiveClip(null);
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
                const res = await api.post('/search/nl', payload);
                setNlMeta({
                    llm_used: res.data.llm_used,
                    cached: res.data.cached,
                    criteria: res.data.criteria,
                    explanation: res.data.explanation,
                });
                setResults(res.data.results || []);
            } else if (mode === 'image') {
                if (!imageQueryFile) {
                    setResults([]);
                    setImageMeta({ query_attributes: {} });
                    return;
                }
                const formData = new FormData();
                formData.append('image', imageQueryFile);
                if (selectedFile) {
                    formData.append('file_id', String(Number(selectedFile)));
                }
                formData.append('top_k', String(MAX_RENDER_RESULTS));
                formData.append('min_score', '0.20');
                const res = await api.post('/search/by-image', formData, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                });
                setImageMeta({ query_attributes: res.data?.query_attributes || {} });
                setResults(res.data?.results || []);
            } else {
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

                const res = await api.post('/search', payload);
                setResults(res.data);
            }
        } catch (err) {
            console.error("Search failed", err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>行人特征检索</h1>

            <div className="stat-card" style={{ marginBottom: '2rem' }}>
                <h3 style={{ marginBottom: '1rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '0.5rem' }}>检索条件</h3>

                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
                    <button
                        onClick={() => setMode('structured')}
                        style={{
                            padding: '6px 10px',
                            borderRadius: '8px',
                            border: '1px solid #cbd5e1',
                            background: mode === 'structured' ? '#eff6ff' : 'white',
                            color: mode === 'structured' ? '#2563eb' : '#64748b',
                            fontWeight: 600
                        }}
                    >
                        结构化筛选
                    </button>
                    <button
                        onClick={() => setMode('nl')}
                        style={{
                            padding: '6px 10px',
                            borderRadius: '8px',
                            border: '1px solid #cbd5e1',
                            background: mode === 'nl' ? '#eef2ff' : 'white',
                            color: mode === 'nl' ? '#4f46e5' : '#64748b',
                            fontWeight: 600,
                            display: 'inline-flex',
                            gap: '0.4rem',
                            alignItems: 'center'
                        }}
                    >
                        <Sparkles size={16} /> 自然语言检索
                    </button>
                    <button
                        onClick={() => setMode('image')}
                        style={{
                            padding: '6px 10px',
                            borderRadius: '8px',
                            border: '1px solid #cbd5e1',
                            background: mode === 'image' ? '#ecfdf5' : 'white',
                            color: mode === 'image' ? '#047857' : '#64748b',
                            fontWeight: 600,
                            display: 'inline-flex',
                            gap: '0.4rem',
                            alignItems: 'center'
                        }}
                    >
                        <ImageUp size={16} /> 以图搜人
                    </button>
                    {mode === 'nl' ? (
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', color: '#475569', marginLeft: '0.25rem' }}>
                            <input type="checkbox" checked={useLLM} onChange={(e) => setUseLLM(e.target.checked)} />
                            使用LLM解析（无Key自动降级）
                        </label>
                    ) : null}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', alignItems: 'end' }}>
                    <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>选择目标文件</label>
                        <select
                            value={selectedFile}
                            onChange={(e) => setSelectedFile(e.target.value)}
                            style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                        >
                            <option value="">-- 请选择已分析文件 --</option>
                            {files.map(f => (
                                <option key={f.id} value={f.id}>{f.filename}</option>
                            ))}
                        </select>
                    </div>

                    {mode === 'nl' ? (
                        <div style={{ gridColumn: '1/-1' }}>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>自然语言</label>
                            <input
                                value={nlQuery}
                                onChange={(e) => setNlQuery(e.target.value)}
                                placeholder="例如：找戴帽子背包的男性，14:00-16:00出现，上衣黑色"
                                style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                            />
                        </div>
                    ) : null}
                    {mode === 'image' ? (
                        <div style={{ gridColumn: '1/-1' }}>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>上传行人图片</label>
                            <input
                                type="file"
                                accept="image/*"
                                onChange={handleImageQueryFileChange}
                                style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                            />
                            {imageQueryFile ? (
                                <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: '#475569' }}>
                                    当前图片: {imageQueryFile.name}
                                </div>
                            ) : null}
                        </div>
                    ) : null}

                    <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>性别</label>
                        <select
                            value={filters.gender}
                            onChange={(e) => setFilters({ ...filters, gender: e.target.value })}
                            style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                        >
                            <option value="All">不限</option>
                            <option value="Male">Male</option>
                            <option value="Female">Female</option>
                        </select>
                    </div>

                    <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>上衣颜色</label>
                        <select
                            value={filters.upper_color}
                            onChange={(e) => setFilters({ ...filters, upper_color: e.target.value })}
                            style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                        >
                            <option value="All">不限</option>
                            <option value="Red">Red</option>
                            <option value="Blue">Blue</option>
                            <option value="Black">Black</option>
                            <option value="White">White</option>
                            <option value="Grey">Grey</option>
                            <option value="Green">Green</option>
                            <option value="Yellow">Yellow</option>
                            <option value="Khaki">Khaki</option>
                        </select>
                    </div>

                    <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>配饰/特征</label>
                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                            {[
                                { key: 'has_backpack', label: 'Backpack' },
                                { key: 'has_bag', label: 'HandBag' },
                                { key: 'has_hat', label: 'Hat' },
                                { key: 'has_glasses', label: 'Glasses' },
                            ].map(({ key, label }) => (
                                <button
                                    key={key}
                                    onClick={() => setFilters({ ...filters, [key]: !filters[key] })}
                                    style={{
                                        padding: '4px 8px',
                                        borderRadius: '4px',
                                        border: '1px solid #cbd5e1',
                                        background: filters[key] ? '#eff6ff' : 'white',
                                        color: filters[key] ? '#2563eb' : '#64748b',
                                        fontSize: '0.8rem'
                                    }}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>朝向</label>
                        <select
                            value={filters.orientation || 'All'}
                            onChange={(e) => setFilters({ ...filters, orientation: e.target.value })}
                            style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                        >
                            <option value="All">不限</option>
                            <option value="Front">正面</option>
                            <option value="Side">侧面</option>
                            <option value="Back">背面</option>
                        </select>
                    </div>

                    <button
                        className="btn-primary"
                        onClick={handleSearch}
                        disabled={loading || (mode === 'image' && !imageQueryFile)}
                        style={{ height: '42px', justifyContent: 'center' }}
                    >
                        {loading ? '检索中...' : <><Search size={18} /> 开始检索</>}
                    </button>
                </div>

                {mode === 'nl' && nlMeta ? (
                    <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #e2e8f0', color: '#475569', lineHeight: 1.8 }}>
                        <div>
                            解析方式：{nlMeta.llm_used ? 'LLM' : '规则'} {nlMeta.cached ? '（缓存命中）' : ''}
                        </div>
                        {nlMeta.explanation ? <div>解释：{nlMeta.explanation}</div> : null}
                        {nlMeta.criteria ? (
                            <div style={{ fontSize: '0.9rem' }}>
                                条件：<code style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: '6px' }}>{JSON.stringify(nlMeta.criteria)}</code>
                            </div>
                        ) : null}
                    </div>
                ) : null}
                {mode === 'image' && imageMeta ? (
                    <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #e2e8f0', color: '#475569', lineHeight: 1.8 }}>
                        <div>查询图像属性：</div>
                        <div style={{ fontSize: '0.9rem' }}>
                            <code style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: '6px' }}>
                                {JSON.stringify(imageMeta.query_attributes || {})}
                            </code>
                        </div>
                    </div>
                ) : null}
            </div>

            {activeClip && (
                <div ref={clipRef} className="stat-card" style={{ marginBottom: '2rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                        <div>
                            <h3 style={{ margin: 0 }}>片段播放</h3>
                            <div style={{ fontSize: '0.85rem', color: '#64748b', marginTop: '0.25rem' }}>
                                {activeClip.filename} · {activeClip.cameraLocation}
                                {activeClip.realTime ? ` · ${activeClip.realTime}` : ''}
                            </div>
                        </div>
                        <button
                            onClick={() => setActiveClip(null)}
                            style={{
                                border: '1px solid #e2e8f0',
                                background: 'white',
                                borderRadius: '0.5rem',
                                padding: '0.35rem 0.75rem',
                                cursor: 'pointer',
                                color: '#64748b'
                            }}
                        >
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
                        style={{ width: '100%', borderRadius: '0.75rem', background: '#0f172a' }}
                    />
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem', flexWrap: 'wrap', gap: '0.75rem' }}>
                        <div style={{ fontSize: '0.85rem', color: '#64748b' }}>
                            片段 {formatTime(activeClip.clipStart)} - {formatTime(activeClip.clipEnd)}（目标 {formatTime(activeClip.timestamp)}）
                        </div>
                        <button
                            className="btn-primary"
                            onClick={replayClip}
                            style={{ padding: '0.5rem 0.75rem', fontSize: '0.85rem' }}
                        >
                            重播片段
                        </button>
                    </div>
                </div>
            )}

            {searched && (
                <div>
                    <h3 style={{ marginBottom: '0.4rem' }}>检索结果 ({displayResults.length})</h3>
                    {hiddenCount > 0 && (
                        <div style={{ marginBottom: '1rem', fontSize: '0.85rem', color: '#64748b' }}>
                            已折叠重复/超量结果 {hiddenCount} 条（同一 person_id 仅展示一次）
                        </div>
                    )}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1.5rem' }}>
                        {displayResults.map((item, index) => {
                            const canPlay = item.is_video && item.snippet_info?.timestamp !== undefined;
                            const itemKey = getResultKey(item, index);
                            const isActive = activeClip?.key === itemKey;

                            return (
                                <div
                                    key={itemKey}
                                    className="stat-card"
                                    onClick={() => canPlay && openClip(item)}
                                    style={{
                                        padding: '1rem',
                                        cursor: canPlay ? 'pointer' : 'default',
                                        borderColor: isActive ? '#2563eb' : undefined,
                                        boxShadow: isActive ? '0 0 0 2px rgba(37, 99, 235, 0.15)' : undefined
                                    }}
                                >
                                    <div style={{ aspectRatio: '3/4', background: '#f1f5f9', borderRadius: '0.5rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                                        {item.snippet_info.thumbnail ? (
                                            <img
                                                src={apiUrl(`/thumbnails/${item.snippet_info.thumbnail}`)}
                                                alt="行人缩略图"
                                                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                                onError={(e) => { e.target.style.display = 'none'; }}
                                            />
                                        ) : (
                                            <PlayCircle size={48} color="#cbd5e1" />
                                        )}
                                    </div>
                                    <div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                                            <span style={{ fontWeight: 600 }}>{item.camera_location}</span>
                                            <div style={{ textAlign: 'right', fontSize: '0.8rem', color: '#64748b' }}>
                                                {item.real_time && <div style={{ fontWeight: 500 }}>{item.real_time}</div>}
                                                {item.snippet_info.timestamp !== undefined && (
                                                    <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                                                        视频 {Math.floor(item.snippet_info.timestamp / 60)}:{String(Math.floor(item.snippet_info.timestamp % 60)).padStart(2, '0')}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                                            <span className="badge" style={{ fontSize: '0.75rem', padding: '0.1rem 0.5rem' }}>
                                                {item.snippet_info.attributes.gender}
                                            </span>
                                            <span className="badge" style={{ fontSize: '0.75rem', padding: '0.1rem 0.5rem', background: '#f59e0b' }}>
                                                {item.snippet_info.attributes.upper_color}
                                            </span>
                                            {item.snippet_info.person_id ? (
                                                <span className="badge" style={{ fontSize: '0.75rem', padding: '0.1rem 0.5rem', background: '#e2e8f0', color: '#334155' }}>
                                                    {item.snippet_info.person_id}
                                                </span>
                                            ) : null}
                                        </div>
                                        <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: canPlay ? '#2563eb' : '#94a3b8' }}>
                                            {canPlay ? '点击播放片段' : '无可播放片段'}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                        {displayResults.length === 0 && (
                            <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: '3rem', color: '#94a3b8' }}>
                                未找到符合条件的行人目标
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default Retrieval;
