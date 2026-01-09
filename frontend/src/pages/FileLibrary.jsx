import { useState, useEffect } from 'react';
import axios from 'axios';
import { Upload, FileVideo, FileImage, Trash2, Search, BarChart2, Loader2, CheckCircle, AlertCircle, Calendar } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const FileLibrary = () => {
    const [files, setFiles] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [processing, setProcessing] = useState(null);
    const [showUploadModal, setShowUploadModal] = useState(false);
    const [selectedUploadFile, setSelectedUploadFile] = useState(null);
    const [startTime, setStartTime] = useState('');
    const navigate = useNavigate();

    const fetchFiles = async () => {
        try {
            const res = await axios.get('http://localhost:8000/files');
            setFiles(res.data);
        } catch (err) {
            console.error("Failed to fetch files", err);
        }
    };

    useEffect(() => {
        fetchFiles();
    }, []);

    const handleFileSelect = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        setSelectedUploadFile(file);
        // 默认设置为当前时间
        const now = new Date();
        const localISOTime = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        setStartTime(localISOTime);
        setShowUploadModal(true);
    };

    const handleUpload = async () => {
        if (!selectedUploadFile) return;

        setUploading(true);
        setShowUploadModal(false);
        const formData = new FormData();
        formData.append('file', selectedUploadFile);
        if (startTime) {
            formData.append('start_time', startTime);
        }

        try {
            await axios.post('http://localhost:8000/files/upload', formData);
            await fetchFiles();
        } catch (err) {
            alert("Upload failed");
        } finally {
            setUploading(false);
            setSelectedUploadFile(null);
            setStartTime('');
        }
    };

    const cancelUpload = () => {
        setShowUploadModal(false);
        setSelectedUploadFile(null);
        setStartTime('');
    };

    const handleDelete = async (id, e) => {
        e.stopPropagation();
        if (!confirm("确定删除此文件吗？")) return;
        try {
            await axios.delete(`http://localhost:8000/files/${id}`);
            setFiles(files.filter(f => f.id !== id));
        } catch (err) {
            alert("Delete failed");
        }
    };

    const handleAnalyze = async (file) => {
        if (file.status === 'analyzed') return; // Already done

        setProcessing(file.id);
        try {
            await axios.post(`http://localhost:8000/analyze/${file.id}`);
            // 使用函数式更新避免闭包陈旧问题
            setFiles(prevFiles => prevFiles.map(f => f.id === file.id ? { ...f, status: 'analyzed' } : f));
            // 重新获取最新列表确保数据一致
            await fetchFiles();
        } catch (err) {
            console.error("Analysis failed", err);
            alert("Analysis failed");
        } finally {
            setProcessing(null);
        }
    };

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h1 style={{ fontSize: '1.8rem', margin: 0 }}>媒体文件库</h1>
                <div>
                    <input
                        type="file"
                        id="upload-input"
                        style={{ display: 'none' }}
                        onChange={handleFileSelect}
                        accept="image/*,video/mp4"
                    />
                    <button
                        className="btn-primary"
                        onClick={() => document.getElementById('upload-input').click()}
                        disabled={uploading}
                    >
                        {uploading ? <Loader2 className="animate-spin" size={20} /> : <Upload size={20} />}
                        上传素材
                    </button>
                </div>
            </div>

            {/* 上传时间设置模态框 */}
            {showUploadModal && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                    background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
                }}>
                    <div style={{ background: 'white', padding: '2rem', borderRadius: '1rem', width: '400px', maxWidth: '90%' }}>
                        <h3 style={{ marginBottom: '1.5rem', fontSize: '1.2rem' }}>设置视频开始时间</h3>
                        <p style={{ marginBottom: '1rem', color: '#64748b', fontSize: '0.9rem' }}>
                            文件: {selectedUploadFile?.name}
                        </p>
                        <div style={{ marginBottom: '1.5rem' }}>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500, fontSize: '0.9rem' }}>
                                <Calendar size={16} style={{ display: 'inline', marginRight: '0.5rem' }} />
                                视频开始时间
                            </label>
                            <input
                                type="datetime-local"
                                value={startTime}
                                onChange={(e) => setStartTime(e.target.value)}
                                style={{ width: '100%', padding: '0.6rem', borderRadius: '0.5rem', border: '1px solid #cbd5e1' }}
                            />
                            <p style={{ marginTop: '0.5rem', color: '#94a3b8', fontSize: '0.8rem' }}>
                                用于客流统计时计算真实时间点
                            </p>
                        </div>
                        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                            <button
                                onClick={cancelUpload}
                                style={{ padding: '0.5rem 1rem', border: '1px solid #cbd5e1', borderRadius: '0.5rem', background: 'white', cursor: 'pointer' }}
                            >
                                取消
                            </button>
                            <button
                                className="btn-primary"
                                onClick={handleUpload}
                            >
                                上传
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1.5rem' }}>
                {files.map((file) => (
                    <div key={file.id} className="stat-card" style={{ padding: '0', overflow: 'hidden', position: 'relative' }}>
                        <div style={{
                            height: '160px',
                            background: '#f8fafc',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            borderBottom: '1px solid #e2e8f0'
                        }}>
                            {file.file_type === 'video' ? <FileVideo size={48} color="#94a3b8" /> : <FileImage size={48} color="#94a3b8" />}
                        </div>

                        <div style={{ padding: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '0.5rem' }}>
                                <h3 style={{ margin: 0, fontSize: '1rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '180px' }} title={file.filename}>
                                    {file.filename}
                                </h3>
                                <button onClick={(e) => handleDelete(file.id, e)} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#ef4444' }}>
                                    <Trash2 size={16} />
                                </button>
                            </div>

                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
                                <div>
                                    {file.status === 'analyzed' ? (
                                        <span className="badge" style={{ background: '#dcfce7', color: '#166534', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <CheckCircle size={12} /> 已分析
                                        </span>
                                    ) : processing === file.id ? (
                                        <span className="badge" style={{ background: '#eff6ff', color: '#1e40af', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <Loader2 size={12} className="animate-spin" /> 分析中
                                        </span>
                                    ) : (
                                        <button
                                            onClick={() => handleAnalyze(file)}
                                            style={{ fontSize: '0.8rem', color: '#2563eb', background: 'none', border: '1px solid #2563eb', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer' }}
                                        >
                                            点击分析
                                        </button>
                                    )}
                                </div>

                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                    <button
                                        title="去检索"
                                        disabled={file.status !== 'analyzed'}
                                        onClick={() => navigate('/retrieval', { state: { fileId: file.id } })}
                                        style={{ border: 'none', background: 'transparent', cursor: 'pointer', opacity: file.status === 'analyzed' ? 1 : 0.3 }}
                                    >
                                        <Search size={20} color="#64748b" />
                                    </button>
                                    <button
                                        title="查看客流"
                                        disabled={file.status !== 'analyzed'}
                                        onClick={() => navigate('/traffic', { state: { fileId: file.id } })}
                                        style={{ border: 'none', background: 'transparent', cursor: 'pointer', opacity: file.status === 'analyzed' ? 1 : 0.3 }}
                                    >
                                        <BarChart2 size={20} color="#64748b" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                ))}

                {files.length === 0 && (
                    <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: '4rem', color: '#94a3b8', border: '2px dashed #cbd5e1', borderRadius: '1rem' }}>
                        暂无文件，请上传
                    </div>
                )}
            </div>
        </div>
    );
};

export default FileLibrary;
