import { useEffect, useState } from 'react';
import axios from 'axios';
import { Trash2 } from 'lucide-react';

const History = () => {
    const [records, setRecords] = useState([]);

    const fetchHistory = async () => {
        try {
            const res = await axios.get('http://localhost:8000/history');
            setRecords(res.data);
        } catch (err) {
            console.error("Failed to fetch history", err);
        }
    };

    useEffect(() => {
        fetchHistory();
    }, []);

    const handleDelete = async (id) => {
        if (!confirm("确定删除此记录吗？")) return;
        try {
            await axios.delete(`http://localhost:8000/history/${id}`);
            setRecords(records.filter(r => r.id !== id));
        } catch (err) {
            console.error("Failed to delete", err);
            alert("删除失败");
        }
    };

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>历史记录</h1>
            <div className="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>文件名</th>
                            <th>上传时间</th>
                            <th>识别行人数</th>
                            <th>状态</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {records.map((record) => (
                            <tr key={record.id}>
                                <td>#{record.id}</td>
                                <td>{record.filename}</td>
                                <td>{new Date(record.upload_time).toLocaleString()}</td>
                                <td>
                                    <span style={{ fontWeight: 'bold' }}>{record.pedestrian_count}</span> 人
                                </td>
                                <td>
                                    <span style={{
                                        background: '#dcfce7', color: '#166534',
                                        padding: '0.25rem 0.75rem', borderRadius: '999px', fontSize: '0.875rem'
                                    }}>
                                        完成
                                    </span>
                                </td>
                                <td>
                                    <button
                                        onClick={() => handleDelete(record.id)}
                                        style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#ef4444' }}
                                        title="删除记录"
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {records.length === 0 && (
                            <tr>
                                <td colSpan="6" style={{ textAlign: 'center', padding: '3rem', color: '#94a3b8' }}>
                                    暂无记录
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default History;

