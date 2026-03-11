import { useState, useEffect } from 'react';
import { User, LogOut, Shield, Users, Plus, Trash2, Key, Settings2, Zap, CheckCircle, XCircle, Loader2, Bot } from 'lucide-react';
import { api } from '../lib/api';

const Settings = ({ user, onLogout }) => {
    const [users, setUsers] = useState([]);
    const [showAddUser, setShowAddUser] = useState(false);
    const [newUsername, setNewUsername] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [newRole, setNewRole] = useState('user');

    // LLM 配置状态
    const [llmConfig, setLlmConfig] = useState({
        apiKey: '',
        baseUrl: 'https://api.openai.com/v1',
        model: 'gpt-4o-mini'
    });
    const [llmConfigLoaded, setLlmConfigLoaded] = useState(false);
    const [llmApiKeySet, setLlmApiKeySet] = useState(false);
    const [llmApiKeyPreview, setLlmApiKeyPreview] = useState('');
    const [llmSaving, setLlmSaving] = useState(false);
    const [llmTesting, setLlmTesting] = useState(false);
    const [llmTestResult, setLlmTestResult] = useState(null);
    const [llmSaveMessage, setLlmSaveMessage] = useState(null);

    const fetchUsers = async () => {
        try {
            const res = await api.get('/users');
            setUsers(res.data);
        } catch (err) {
            console.error(err);
        }
    };

    const fetchLLMConfig = async () => {
        try {
            const res = await api.get('/settings/llm');
            setLlmApiKeySet(res.data.api_key_set);
            setLlmApiKeyPreview(res.data.api_key_preview || '');
            setLlmConfig(prev => ({
                ...prev,
                baseUrl: res.data.base_url || 'https://api.openai.com/v1',
                model: res.data.model || 'gpt-4o-mini'
            }));
            setLlmConfigLoaded(true);
        } catch (err) {
            console.error('Failed to load LLM config:', err);
            setLlmConfigLoaded(true);
        }
    };

    useEffect(() => {
        if (user?.role === 'admin') {
            fetchUsers();
        }
        fetchLLMConfig();
    }, [user]);

    const handleAddUser = async (e) => {
        e.preventDefault();
        try {
            await api.post('/users', {
                username: newUsername,
                password: newPassword,
                role: newRole
            });
            setShowAddUser(false);
            setNewUsername('');
            setNewPassword('');
            setNewRole('user');
            fetchUsers();
        } catch (err) {
            alert(err.response?.data?.detail || '添加失败');
        }
    };

    const handleDeleteUser = async (id) => {
        if (!confirm('确定删除此用户吗？')) return;
        try {
            await api.delete(`/users/${id}`);
            fetchUsers();
        } catch (err) {
            alert(err.response?.data?.detail || '删除失败');
        }
    };

    const handleLogout = () => {
        localStorage.removeItem('user');
        localStorage.removeItem('token');
        onLogout();
    };

    const handleSaveLLMConfig = async () => {
        setLlmSaving(true);
        setLlmSaveMessage(null);
        setLlmTestResult(null);

        try {
            const payload = {
                base_url: llmConfig.baseUrl,
                model: llmConfig.model
            };
            // 只有当用户输入了新的 API Key 时才发送
            if (llmConfig.apiKey) {
                payload.api_key = llmConfig.apiKey;
            }

            await api.post('/settings/llm', payload);
            setLlmSaveMessage({ type: 'success', text: '配置已保存！' });
            setLlmConfig(prev => ({ ...prev, apiKey: '' })); // 清空输入的密钥
            fetchLLMConfig(); // 重新加载配置
        } catch (err) {
            setLlmSaveMessage({ type: 'error', text: err.response?.data?.detail || '保存失败' });
        } finally {
            setLlmSaving(false);
        }
    };

    const handleTestLLMConnection = async () => {
        setLlmTesting(true);
        setLlmTestResult(null);

        try {
            const res = await api.post('/settings/llm/test');
            setLlmTestResult(res.data);
        } catch (err) {
            setLlmTestResult({ success: false, message: err.response?.data?.detail || '测试失败' });
        } finally {
            setLlmTesting(false);
        }
    };

    const handleClearLLMKey = async () => {
        if (!confirm('确定要清除 API Key 吗？')) return;
        setLlmSaving(true);
        try {
            await api.post('/settings/llm', { api_key: '' });
            setLlmSaveMessage({ type: 'success', text: 'API Key 已清除' });
            fetchLLMConfig();
        } catch (err) {
            setLlmSaveMessage({ type: 'error', text: '清除失败' });
        } finally {
            setLlmSaving(false);
        }
    };

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>系统设置</h1>

            {/* 当前用户信息 */}
            <div className="stat-card" style={{ marginBottom: '2rem' }}>
                <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <User size={20} />
                    当前账户
                </h3>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <div style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                            {user?.username}
                        </div>
                        <span style={{
                            background: user?.role === 'admin' ? '#dbeafe' : '#f0fdf4',
                            color: user?.role === 'admin' ? '#1d4ed8' : '#16a34a',
                            padding: '0.25rem 0.75rem',
                            borderRadius: '999px',
                            fontSize: '0.875rem'
                        }}>
                            {user?.role === 'admin' ? '管理员' : '普通用户'}
                        </span>
                    </div>
                    <button
                        onClick={handleLogout}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                            padding: '0.75rem 1.5rem',
                            background: '#fee2e2',
                            color: '#dc2626',
                            border: 'none',
                            borderRadius: '0.5rem',
                            cursor: 'pointer',
                            fontWeight: 500
                        }}
                    >
                        <LogOut size={18} />
                        退出登录
                    </button>
                </div>
            </div>

            {/* LLM API 配置 */}
            <div className="stat-card" style={{ marginBottom: '2rem' }}>
                <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Bot size={20} />
                    LLM API 配置
                    <span style={{
                        marginLeft: 'auto',
                        fontSize: '0.75rem',
                        padding: '0.25rem 0.5rem',
                        borderRadius: '999px',
                        background: llmApiKeySet ? '#dcfce7' : '#fef3c7',
                        color: llmApiKeySet ? '#16a34a' : '#d97706'
                    }}>
                        {llmApiKeySet ? '已配置' : '未配置'}
                    </span>
                </h3>

                <div style={{ marginBottom: '1rem', fontSize: '0.9rem', color: '#6b7280' }}>
                    配置 LLM API 后，系统将使用 AI 生成智能洞察和分析报告。支持 OpenAI API 及兼容接口（如 DeepSeek、智谱等）。
                </div>

                {!llmConfigLoaded ? (
                    <div style={{ textAlign: 'center', padding: '2rem', color: '#9ca3af' }}>
                        <Loader2 size={24} className="spin" style={{ animation: 'spin 1s linear infinite' }} />
                        <div>加载配置中...</div>
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        {/* API Key */}
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', fontWeight: 500 }}>
                                API Key
                            </label>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                <input
                                    type="password"
                                    value={llmConfig.apiKey}
                                    onChange={(e) => setLlmConfig(prev => ({ ...prev, apiKey: e.target.value }))}
                                    placeholder={llmApiKeySet ? `当前: ${llmApiKeyPreview}（输入新值将覆盖）` : "sk-xxxxxxxx..."}
                                    style={{
                                        flex: 1,
                                        padding: '0.75rem',
                                        borderRadius: '0.5rem',
                                        border: '1px solid #d1d5db',
                                        fontSize: '0.9rem'
                                    }}
                                />
                                {llmApiKeySet && (
                                    <button
                                        onClick={handleClearLLMKey}
                                        style={{
                                            padding: '0.75rem',
                                            background: '#fee2e2',
                                            color: '#dc2626',
                                            border: 'none',
                                            borderRadius: '0.5rem',
                                            cursor: 'pointer'
                                        }}
                                        title="清除 API Key"
                                    >
                                        <Trash2 size={18} />
                                    </button>
                                )}
                            </div>
                        </div>

                        {/* Base URL */}
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', fontWeight: 500 }}>
                                API Base URL
                            </label>
                            <input
                                type="text"
                                value={llmConfig.baseUrl}
                                onChange={(e) => setLlmConfig(prev => ({ ...prev, baseUrl: e.target.value }))}
                                placeholder="https://api.openai.com/v1"
                                style={{
                                    width: '100%',
                                    padding: '0.75rem',
                                    borderRadius: '0.5rem',
                                    border: '1px solid #d1d5db',
                                    fontSize: '0.9rem'
                                }}
                            />
                            <div style={{ marginTop: '0.25rem', fontSize: '0.8rem', color: '#9ca3af' }}>
                                OpenAI: https://api.openai.com/v1 | DeepSeek: https://api.deepseek.com/v1 | 智谱: https://open.bigmodel.cn/api/paas/v4
                            </div>
                        </div>

                        {/* Model */}
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', fontWeight: 500 }}>
                                模型名称
                            </label>
                            <input
                                type="text"
                                value={llmConfig.model}
                                onChange={(e) => setLlmConfig(prev => ({ ...prev, model: e.target.value }))}
                                placeholder="gpt-4o-mini"
                                style={{
                                    width: '100%',
                                    padding: '0.75rem',
                                    borderRadius: '0.5rem',
                                    border: '1px solid #d1d5db',
                                    fontSize: '0.9rem'
                                }}
                            />
                            <div style={{ marginTop: '0.25rem', fontSize: '0.8rem', color: '#9ca3af' }}>
                                常用模型: gpt-4o-mini, gpt-4o, deepseek-chat, glm-4
                            </div>
                        </div>

                        {/* 操作按钮 */}
                        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
                            <button
                                onClick={handleSaveLLMConfig}
                                disabled={llmSaving}
                                className="btn-primary"
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    padding: '0.75rem 1.5rem',
                                    opacity: llmSaving ? 0.7 : 1
                                }}
                            >
                                {llmSaving ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Key size={16} />}
                                保存配置
                            </button>
                            <button
                                onClick={handleTestLLMConnection}
                                disabled={llmTesting || !llmApiKeySet}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    padding: '0.75rem 1.5rem',
                                    background: llmApiKeySet ? '#f0f9ff' : '#f3f4f6',
                                    color: llmApiKeySet ? '#0369a1' : '#9ca3af',
                                    border: 'none',
                                    borderRadius: '0.5rem',
                                    cursor: llmApiKeySet ? 'pointer' : 'not-allowed',
                                    fontWeight: 500,
                                    opacity: llmTesting ? 0.7 : 1
                                }}
                            >
                                {llmTesting ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Zap size={16} />}
                                测试连接
                            </button>
                        </div>

                        {/* 保存结果消息 */}
                        {llmSaveMessage && (
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.5rem',
                                padding: '0.75rem 1rem',
                                borderRadius: '0.5rem',
                                background: llmSaveMessage.type === 'success' ? '#dcfce7' : '#fee2e2',
                                color: llmSaveMessage.type === 'success' ? '#16a34a' : '#dc2626'
                            }}>
                                {llmSaveMessage.type === 'success' ? <CheckCircle size={18} /> : <XCircle size={18} />}
                                {llmSaveMessage.text}
                            </div>
                        )}

                        {/* 测试结果 */}
                        {llmTestResult && (
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.5rem',
                                padding: '0.75rem 1rem',
                                borderRadius: '0.5rem',
                                background: llmTestResult.success ? '#dcfce7' : '#fee2e2',
                                color: llmTestResult.success ? '#16a34a' : '#dc2626'
                            }}>
                                {llmTestResult.success ? <CheckCircle size={18} /> : <XCircle size={18} />}
                                {llmTestResult.message}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* 用户管理（仅管理员可见） */}
            {user?.role === 'admin' && (
                <div className="stat-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                        <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Users size={20} />
                            用户管理
                        </h3>
                        <button
                            className="btn-primary"
                            onClick={() => setShowAddUser(true)}
                            style={{ padding: '0.5rem 1rem' }}
                        >
                            <Plus size={16} /> 添加用户
                        </button>
                    </div>

                    {/* 添加用户表单 */}
                    {showAddUser && (
                        <form onSubmit={handleAddUser} style={{
                            background: '#f8fafc',
                            padding: '1.5rem',
                            borderRadius: '0.5rem',
                            marginBottom: '1.5rem'
                        }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '1rem', alignItems: 'end' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem' }}>用户名</label>
                                    <input
                                        type="text"
                                        value={newUsername}
                                        onChange={(e) => setNewUsername(e.target.value)}
                                        style={{ width: '100%', padding: '0.5rem', borderRadius: '0.375rem', border: '1px solid #d1d5db' }}
                                        required
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem' }}>密码</label>
                                    <input
                                        type="password"
                                        value={newPassword}
                                        onChange={(e) => setNewPassword(e.target.value)}
                                        style={{ width: '100%', padding: '0.5rem', borderRadius: '0.375rem', border: '1px solid #d1d5db' }}
                                        required
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem' }}>角色</label>
                                    <select
                                        value={newRole}
                                        onChange={(e) => setNewRole(e.target.value)}
                                        style={{ width: '100%', padding: '0.5rem', borderRadius: '0.375rem', border: '1px solid #d1d5db' }}
                                    >
                                        <option value="user">普通用户</option>
                                        <option value="admin">管理员</option>
                                    </select>
                                </div>
                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                    <button type="submit" className="btn-primary" style={{ padding: '0.5rem 1rem' }}>
                                        添加
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setShowAddUser(false)}
                                        style={{ padding: '0.5rem 1rem', border: '1px solid #d1d5db', borderRadius: '0.375rem', background: 'white', cursor: 'pointer' }}
                                    >
                                        取消
                                    </button>
                                </div>
                            </div>
                        </form>
                    )}

                    {/* 用户列表 */}
                    <div className="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>用户名</th>
                                    <th>角色</th>
                                    <th>创建时间</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users.map((u) => (
                                    <tr key={u.id}>
                                        <td>#{u.id}</td>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                {u.role === 'admin' && <Shield size={14} color="#1d4ed8" />}
                                                {u.username}
                                            </div>
                                        </td>
                                        <td>
                                            <span style={{
                                                background: u.role === 'admin' ? '#dbeafe' : '#f0fdf4',
                                                color: u.role === 'admin' ? '#1d4ed8' : '#16a34a',
                                                padding: '0.2rem 0.5rem',
                                                borderRadius: '999px',
                                                fontSize: '0.8rem'
                                            }}>
                                                {u.role === 'admin' ? '管理员' : '用户'}
                                            </span>
                                        </td>
                                        <td>{new Date(u.created_at).toLocaleString()}</td>
                                        <td>
                                            {u.username !== 'admin' && (
                                                <button
                                                    onClick={() => handleDeleteUser(u.id)}
                                                    style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#ef4444' }}
                                                    title="删除用户"
                                                >
                                                    <Trash2 size={16} />
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            <style>{`
                @keyframes spin {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }
            `}</style>
        </div>
    );
};

export default Settings;
