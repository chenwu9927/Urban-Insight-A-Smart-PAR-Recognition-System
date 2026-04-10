import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { formatDateTime } from '../lib/time';

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

function buildResultTitle(item) {
    const attrs = item?.snippet_info?.attributes || {};
    return [
        translate(attrs.gender, genderLabels),
        translate(attrs.age_group, ageGroupLabels),
        translate(attrs.upper_color, colorLabels),
    ]
        .filter((part) => part && part !== '--')
        .join(' · ') || '识别结果';
}

function Retrieval() {
    const location = useLocation();
    const navigate = useNavigate();
    const imageInputRef = useRef(null);
    const [files, setFiles] = useState([]);
    const [mode, setMode] = useState('structured');
    const [selectedFile, setSelectedFile] = useState(location.state?.fileId ? String(location.state.fileId) : '');
    const [filters, setFilters] = useState(defaultFilters);
    const [queryText, setQueryText] = useState('');
    const [queryImage, setQueryImage] = useState(null);
    const [results, setResults] = useState([]);
    const [searchNote, setSearchNote] = useState('');
    const [loading, setLoading] = useState(false);
    const [pageError, setPageError] = useState('');
    const [useLLM, setUseLLM] = useState(true);

    useEffect(() => {
        const loadFiles = async () => {
            try {
                const response = await api.get('/files');
                setFiles(response.data || []);
            } catch (error) {
                console.error('Failed to load files for retrieval', error);
            }
        };
        void loadFiles();
    }, []);

    const selectedFileLabel = useMemo(
        () => files.find((item) => String(item.id) === String(selectedFile))?.filename || '',
        [files, selectedFile],
    );

    const handleStructuredSearch = async () => {
        const payload = {
            ...filters,
            file_id: selectedFile ? Number(selectedFile) : null,
        };
        const response = await api.post('/search', payload);
        setResults(response.data || []);
        setSearchNote(`找到 ${(response.data || []).length} 条结果。`);
    };

    const handleNlSearch = async () => {
        const response = await api.post('/search/nl', {
            query: queryText,
            file_id: selectedFile ? Number(selectedFile) : null,
            use_llm: useLLM ? 1 : 0,
        });
        setResults(response.data?.results || []);
        setSearchNote(response.data?.explanation || '已完成语义检索。');
    };

    const handleImageSearch = async () => {
        if (!queryImage) {
            throw new Error('请先选择一张查询图片。');
        }
        const formData = new FormData();
        formData.append('image', queryImage);
        if (selectedFile) {
            formData.append('file_id', String(Number(selectedFile)));
        }
        const response = await api.post('/search/by-image', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
        setResults(response.data?.results || []);
        setSearchNote(`已根据图片完成检索，找到 ${(response.data?.results || []).length} 条结果。`);
    };

    const handleSearch = async () => {
        setLoading(true);
        setPageError('');
        try {
            if (mode === 'structured') {
                await handleStructuredSearch();
            } else if (mode === 'nl') {
                await handleNlSearch();
            } else {
                await handleImageSearch();
            }
        } catch (error) {
            console.error('Failed to search', error);
            setPageError(error?.response?.data?.detail || error.message || '检索失败。');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="page-shell">
            <section className="card subtle-card">
                <div className="card-title-row">
                    <div>
                        <div className="list-row-title">事件与检索</div>
                        <div className="list-row-subtitle">结构化检索、语义描述和以图搜人都会汇总在这里。</div>
                    </div>
                    <div className="segmented-control">
                        {modeOptions.map((option) => (
                            <button
                                key={option.id}
                                type="button"
                                className={`segmented-item ${mode === option.id ? 'active' : ''}`}
                                onClick={() => setMode(option.id)}
                            >
                                {option.label}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="form-grid compact-form-grid" style={{ marginTop: 16 }}>
                    <div className="form-field">
                        <label>范围</label>
                        <select value={selectedFile} onChange={(event) => setSelectedFile(event.target.value)}>
                            <option value="">全部文件</option>
                            {files.map((file) => (
                                <option key={file.id} value={file.id}>
                                    {file.filename}
                                </option>
                            ))}
                        </select>
                    </div>

                    {mode === 'structured' ? (
                        <>
                            <div className="form-field">
                                <label>性别</label>
                                <select value={filters.gender} onChange={(event) => setFilters((current) => ({ ...current, gender: event.target.value }))}>
                                    <option value="All">全部</option>
                                    <option value="Male">男</option>
                                    <option value="Female">女</option>
                                </select>
                            </div>
                            <div className="form-field">
                                <label>年龄</label>
                                <select
                                    value={filters.age_group}
                                    onChange={(event) => setFilters((current) => ({ ...current, age_group: event.target.value }))}
                                >
                                    <option value="All">全部</option>
                                    <option value="Child">儿童</option>
                                    <option value="Teen">青少年</option>
                                    <option value="Young">青年</option>
                                    <option value="Adult">成人</option>
                                    <option value="Old">老年</option>
                                </select>
                            </div>
                            <div className="form-field">
                                <label>上衣颜色</label>
                                <select
                                    value={filters.upper_color}
                                    onChange={(event) => setFilters((current) => ({ ...current, upper_color: event.target.value }))}
                                >
                                    <option value="All">全部</option>
                                    {Object.keys(colorLabels).map((key) => (
                                        <option key={key} value={key}>
                                            {colorLabels[key]}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="form-field">
                                <label>朝向</label>
                                <select
                                    value={filters.orientation}
                                    onChange={(event) => setFilters((current) => ({ ...current, orientation: event.target.value }))}
                                >
                                    <option value="All">全部</option>
                                    {Object.keys(orientationLabels).map((key) => (
                                        <option key={key} value={key}>
                                            {orientationLabels[key]}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <label className="checkbox-row">
                                <input
                                    type="checkbox"
                                    checked={filters.has_backpack}
                                    onChange={(event) => setFilters((current) => ({ ...current, has_backpack: event.target.checked }))}
                                />
                                <span>背包</span>
                            </label>
                            <label className="checkbox-row">
                                <input
                                    type="checkbox"
                                    checked={filters.has_hat}
                                    onChange={(event) => setFilters((current) => ({ ...current, has_hat: event.target.checked }))}
                                />
                                <span>帽子</span>
                            </label>
                            <label className="checkbox-row">
                                <input
                                    type="checkbox"
                                    checked={filters.has_bag}
                                    onChange={(event) => setFilters((current) => ({ ...current, has_bag: event.target.checked }))}
                                />
                                <span>手提包</span>
                            </label>
                            <label className="checkbox-row">
                                <input
                                    type="checkbox"
                                    checked={filters.has_glasses}
                                    onChange={(event) => setFilters((current) => ({ ...current, has_glasses: event.target.checked }))}
                                />
                                <span>眼镜</span>
                            </label>
                        </>
                    ) : null}

                    {mode === 'nl' ? (
                        <>
                            <div className="form-field form-field-span-2">
                                <label>语义描述</label>
                                <textarea value={queryText} onChange={(event) => setQueryText(event.target.value)} placeholder="例如：检索穿深色上衣、背包、在入口处出现的人" />
                            </div>
                            <label className="checkbox-row">
                                <input type="checkbox" checked={useLLM} onChange={(event) => setUseLLM(event.target.checked)} />
                                <span>使用模型解析</span>
                            </label>
                        </>
                    ) : null}

                    {mode === 'image' ? (
                        <>
                            <input
                                ref={imageInputRef}
                                type="file"
                                accept="image/*"
                                style={{ display: 'none' }}
                                onChange={(event) => setQueryImage(event.target.files?.[0] || null)}
                            />
                            <div className="form-field form-field-span-2">
                                <label>查询图片</label>
                                <div className="action-row">
                                    <button type="button" className="btn-ghost" onClick={() => imageInputRef.current?.click()}>
                                        选择图片
                                    </button>
                                    <span>{queryImage?.name || '未选择图片'}</span>
                                </div>
                            </div>
                        </>
                    ) : null}
                </div>

                <div className="action-row" style={{ marginTop: 16 }}>
                    <button type="button" className="btn-primary" onClick={handleSearch} disabled={loading}>
                        {loading ? '检索中…' : '开始检索'}
                    </button>
                    {selectedFileLabel ? <span className="list-row-subtitle">当前范围：{selectedFileLabel}</span> : null}
                </div>
                {pageError ? <div className="notice error">{pageError}</div> : null}
                {searchNote ? <div className="notice success">{searchNote}</div> : null}
            </section>

            <section className="card">
                <div className="list-row-title">检索结果</div>
                <div className="list compact-list" style={{ marginTop: 12 }}>
                    {results.map((item, index) => {
                        const attrs = item?.snippet_info?.attributes || {};
                        const accessoryTags = getAccessoryTags(attrs);
                        return (
                            <div key={`${item.record_id}-${index}`} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{buildResultTitle(item)}</div>
                                    <div className="list-row-subtitle">
                                        {item.filename} · {item.camera_location || '未标注点位'} · {item.real_time || formatDateTime(item.upload_time)}
                                    </div>
                                    <div className="list-row-subtitle">
                                        朝向 {translate(attrs.orientation, orientationLabels)}
                                        {accessoryTags.length ? ` · ${accessoryTags.join(' / ')}` : ''}
                                        {item?.snippet_info?.match_score ? ` · 匹配 ${Number(item.snippet_info.match_score).toFixed(2)}` : ''}
                                    </div>
                                </div>
                                <div className="list-row-meta">
                                    <button
                                        type="button"
                                        className="btn-ghost"
                                        onClick={() => navigate(`/tasks/${item.file_id || item.record_id}`)}
                                    >
                                        打开
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                    {!results.length ? <div className="empty-state">暂无结果。</div> : null}
                </div>
            </section>
        </div>
    );
}

export default Retrieval;
