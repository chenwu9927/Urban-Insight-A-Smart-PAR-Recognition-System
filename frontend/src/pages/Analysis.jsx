import { useState } from 'react'
import axios from 'axios'
import { Upload, ImageIcon, Loader2, Video } from 'lucide-react'

function Analysis() {
    const [file, setFile] = useState(null)
    const [preview, setPreview] = useState(null)
    const [results, setResults] = useState(null)
    const [loading, setLoading] = useState(false)
    const [isVideo, setIsVideo] = useState(false)

    const handleFileChange = (e) => {
        const selectedFile = e.target.files[0]
        if (selectedFile) {
            setFile(selectedFile)
            setPreview(URL.createObjectURL(selectedFile))
            setResults(null)
            setIsVideo(selectedFile.type.startsWith('video/'))
        }
    }

    const handleUpload = async () => {
        if (!file) return

        setLoading(true)
        const formData = new FormData()
        formData.append('file', file)

        try {
            const response = await axios.post('http://localhost:8000/analyze', formData)
            setResults(response.data)
        } catch (error) {
            console.error('Error uploading file:', error)
            alert('Upload failed!')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>智能属性分析</h1>

            <div style={{ display: 'grid', gridTemplateColumns: results ? '1fr 1fr' : '1fr', gap: '2rem' }}>
                {/* Upload Section */}
                <div>
                    <div className="upload-zone" onClick={() => document.getElementById('fileInput').click()}>
                        <input
                            id="fileInput"
                            type="file"
                            className="input-hidden"
                            accept="image/*,video/mp4"
                            onChange={handleFileChange}
                        />
                        {preview ? (
                            isVideo ? (
                                <video src={preview} controls style={{ maxHeight: '300px', maxWidth: '100%', borderRadius: '8px' }} />
                            ) : (
                                <img src={preview} alt="Preview" style={{ maxHeight: '300px', maxWidth: '100%', borderRadius: '8px' }} />
                            )
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
                                <Upload size={48} color="#94a3b8" />
                                <div>
                                    <p style={{ fontSize: '1.1rem', fontWeight: 500 }}>点击或拖拽上传</p>
                                    <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>支持 JPG, PNG, MP4</p>
                                </div>
                            </div>
                        )}
                    </div>

                    <div style={{ marginTop: '1.5rem', textAlign: 'center' }}>
                        <button className="btn-primary" onClick={handleUpload} disabled={!file || loading}
                            style={{ width: '100%', justifyContent: 'center', padding: '1rem', fontSize: '1.1rem', opacity: (!file || loading) ? 0.7 : 1 }}>
                            {loading ? <Loader2 className="animate-spin" /> : (isVideo ? <Video /> : <ImageIcon />)}
                            {loading ? '正在分析...' : '开始识别'}
                        </button>
                    </div>
                </div>

                {/* Results Section */}
                {results && (
                    <div className="result-card" style={{ marginTop: 0, height: 'fit-content' }}>
                        <h2 style={{ fontSize: '1.25rem', marginBottom: '1.5rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '1rem' }}>
                            分析结果 ({results.pedestrians.length} 目标)
                        </h2>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxHeight: '600px', overflowY: 'auto' }}>
                            {results.pedestrians.map((ped, index) => (
                                <div key={index} className="pedestrian-item">
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                                        <h3 style={{ margin: 0, fontSize: '1rem' }}>
                                            {ped.timestamp !== undefined ? `时间点 ${ped.timestamp}s` : `行人目标 #${index + 1}`}
                                        </h3>
                                        <span style={{ fontSize: '0.9rem', color: '#10b981', fontWeight: 600 }}>
                                            {(ped.attributes.confidence * 100).toFixed(1)}% 置信度
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                                        <span className="badge">{ped.attributes.gender}</span>
                                        <span className="badge">{ped.attributes.age_group}</span>
                                        <span className="badge" style={{ background: '#e2e8f0', color: '#475569' }}>{ped.attributes.orientation || 'Front'}</span>
                                        {ped.attributes.has_backpack && <span className="badge" style={{ background: '#f59e0b' }}>背包</span>}
                                        {ped.attributes.has_hat && <span className="badge" style={{ background: '#8b5cf6' }}>帽子</span>}
                                        {ped.attributes.has_glasses && <span className="badge" style={{ background: '#0ea5e9' }}>眼镜</span>}
                                        {ped.attributes.has_bag && <span className="badge" style={{ background: '#eab308' }}>手提包</span>}
                                    </div>
                                    <div style={{ fontSize: '0.9rem', color: '#475569', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                                        <div style={{ background: 'white', padding: '0.5rem', borderRadius: '4px' }}>
                                            <span style={{ color: '#94a3b8' }}>上装:</span> {ped.attributes.upper_color}
                                        </div>
                                        <div style={{ background: 'white', padding: '0.5rem', borderRadius: '4px' }}>
                                            <span style={{ color: '#94a3b8' }}>下装:</span> {ped.attributes.lower_color}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

export default Analysis
