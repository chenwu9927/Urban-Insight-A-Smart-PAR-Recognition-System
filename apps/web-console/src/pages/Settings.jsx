import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';

function formatDateTime(value) {
    if (!value) return '--';
    try {
        return new Date(value).toLocaleString('zh-CN');
    } catch {
        return value;
    }
}

function Settings({ user, onLogout }) {
    const [users, setUsers] = useState([]);
    const [showAddUser, setShowAddUser] = useState(false);
    const [newUsername, setNewUsername] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [newRole, setNewRole] = useState('user');
    const [llmConfig, setLlmConfig] = useState({
        apiKey: '',
        baseUrl: 'https://api.longcat.chat/openai',
        model: 'LongCat-Flash-Lite',
    });
    const [llmConfigLoaded, setLlmConfigLoaded] = useState(false);
    const [llmApiKeySet, setLlmApiKeySet] = useState(false);
    const [llmApiKeyPreview, setLlmApiKeyPreview] = useState('');
    const [llmSaving, setLlmSaving] = useState(false);
    const [llmTesting, setLlmTesting] = useState(false);
    const [llmTestResult, setLlmTestResult] = useState(null);
    const [llmSaveMessage, setLlmSaveMessage] = useState(null);

    const fetchUsers = useCallback(async () => {
        try {
            const response = await api.get('/users');
            setUsers(response.data || []);
        } catch (error) {
            console.error('Failed to load users', error);
        }
    }, []);

    const fetchLLMConfig = useCallback(async () => {
        try {
            const response = await api.get('/settings/llm');
            setLlmApiKeySet(response.data.api_key_set);
            setLlmApiKeyPreview(response.data.api_key_preview || '');
            setLlmConfig((current) => ({
                ...current,
                baseUrl: response.data.base_url || 'https://api.longcat.chat/openai',
                model: response.data.model || 'LongCat-Flash-Lite',
            }));
        } catch (error) {
            console.error('Failed to load LLM config', error);
        } finally {
            setLlmConfigLoaded(true);
        }
    }, []);

    useEffect(() => {
        if (user?.role === 'admin') {
            void fetchUsers();
        }
        void fetchLLMConfig();
    }, [fetchLLMConfig, fetchUsers, user]);

    const handleAddUser = async (event) => {
        event.preventDefault();
        try {
            await api.post('/users', {
                username: newUsername,
                password: newPassword,
                role: newRole,
            });
            setShowAddUser(false);
            setNewUsername('');
            setNewPassword('');
            setNewRole('user');
            void fetchUsers();
        } catch (error) {
            window.alert(error.response?.data?.detail || '新增用户失败。');
        }
    };

    const handleDeleteUser = async (id) => {
        if (!window.confirm('确定删除这个用户吗？')) {
            return;
        }
        try {
            await api.delete(`/users/${id}`);
            void fetchUsers();
        } catch (error) {
            window.alert(error.response?.data?.detail || '删除用户失败。');
        }
    };

    const handleSaveLLMConfig = async () => {
        setLlmSaving(true);
        setLlmSaveMessage(null);
        setLlmTestResult(null);
        try {
            const payload = {
                base_url: llmConfig.baseUrl,
                model: llmConfig.model,
            };
            if (llmConfig.apiKey) {
                payload.api_key = llmConfig.apiKey;
            }
            await api.post('/settings/llm', payload);
            setLlmSaveMessage({ type: 'success', text: '模型配置已保存。' });
            setLlmConfig((current) => ({ ...current, apiKey: '' }));
            void fetchLLMConfig();
        } catch (error) {
            setLlmSaveMessage({ type: 'error', text: error.response?.data?.detail || '模型配置保存失败。' });
        } finally {
            setLlmSaving(false);
        }
    };

    const handleTestLLMConnection = async () => {
        setLlmTesting(true);
        setLlmTestResult(null);
        try {
            const response = await api.post('/settings/llm/test');
            setLlmTestResult(response.data);
        } catch (error) {
            setLlmTestResult({ success: false, message: error.response?.data?.detail || '连接测试失败。' });
        } finally {
            setLlmTesting(false);
        }
    };

    const handleClearLLMKey = async () => {
        if (!window.confirm('确定清空已保存的 API Key 吗？')) {
            return;
        }
        setLlmSaving(true);
        try {
            await api.post('/settings/llm', { api_key: '' });
            setLlmSaveMessage({ type: 'success', text: 'API Key 已清空。' });
            void fetchLLMConfig();
        } catch {
            setLlmSaveMessage({ type: 'error', text: 'API Key 清空失败。' });
        } finally {
            setLlmSaving(false);
        }
    };

    const handleLogout = () => {
        localStorage.removeItem('user');
        localStorage.removeItem('token');
        onLogout();
    };

    return (
        <div className="page-shell">
            <section className="page-toolbar">
                <div className="page-header-actions">
                    <button type="button" className="btn-secondary" onClick={handleLogout}>
                        退出登录
                    </button>
                </div>
            </section>

            <div className="page-grid-2">
                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">当前账号</h2>
                        </div>
                    </div>
                    <div className="list compact-list">
                        <div className="list-row">
                            <div className="list-row-main">
                                <div className="list-row-title">{user?.username}</div>
                                <div className="list-row-subtitle">当前登录账号</div>
                            </div>
                            <div className="list-row-meta">
                                <span className="status-tag is-info">{user?.role === 'admin' ? '管理员' : '普通用户'}</span>
                            </div>
                        </div>
                    </div>
                </section>

                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">模型状态</h2>
                        </div>
                    </div>
                    <div className="list compact-list">
                        <div className="list-row">
                            <div className="list-row-main">
                                <div className="list-row-title">Base URL</div>
                                <div className="list-row-subtitle">{llmConfig.baseUrl}</div>
                            </div>
                        </div>
                        <div className="list-row">
                            <div className="list-row-main">
                                <div className="list-row-title">模型</div>
                                <div className="list-row-subtitle">{llmConfig.model}</div>
                            </div>
                            <div className="list-row-meta">
                                <span className={`status-tag ${llmApiKeySet ? 'is-success' : 'is-warning'}`}>
                                    {llmApiKeySet ? '已配置 API Key' : '缺少 API Key'}
                                </span>
                            </div>
                        </div>
                    </div>
                </section>
            </div>

            <section className="card">
                <div className="card-header">
                    <div>
                        <h2 className="card-title">模型配置</h2>
                    </div>
                </div>

                {!llmConfigLoaded ? <div className="empty-state">正在加载...</div> : null}

                {llmConfigLoaded ? (
                    <>
                        <div className="field-grid three">
                            <label className="field">
                                <span>API Key</span>
                                <input
                                    type="password"
                                    value={llmConfig.apiKey}
                                    onChange={(event) => setLlmConfig((current) => ({ ...current, apiKey: event.target.value }))}
                                    placeholder={llmApiKeySet ? `当前：${llmApiKeyPreview}` : '请输入新的 API Key'}
                                />
                            </label>
                            <label className="field">
                                <span>Base URL</span>
                                <input
                                    type="text"
                                    value={llmConfig.baseUrl}
                                    onChange={(event) => setLlmConfig((current) => ({ ...current, baseUrl: event.target.value }))}
                                />
                            </label>
                            <label className="field">
                                <span>模型名称</span>
                                <input
                                    type="text"
                                    value={llmConfig.model}
                                    onChange={(event) => setLlmConfig((current) => ({ ...current, model: event.target.value }))}
                                />
                            </label>
                        </div>

                        <div className="action-row">
                            <button type="button" className="btn-primary" onClick={handleSaveLLMConfig} disabled={llmSaving}>
                                {llmSaving ? '保存中...' : '保存配置'}
                            </button>
                            <button
                                type="button"
                                className="btn-secondary"
                                onClick={handleTestLLMConnection}
                                disabled={llmTesting || !llmApiKeySet}
                            >
                                {llmTesting ? '测试中...' : '测试连接'}
                            </button>
                            {llmApiKeySet ? (
                                <button type="button" className="btn-ghost danger" onClick={handleClearLLMKey} disabled={llmSaving}>
                                    清空 API Key
                                </button>
                            ) : null}
                        </div>

                        {llmSaveMessage ? <div className={`notice ${llmSaveMessage.type}`}>{llmSaveMessage.text}</div> : null}
                        {llmTestResult ? (
                            <div className={`notice ${llmTestResult.success ? 'success' : 'error'}`}>{llmTestResult.message}</div>
                        ) : null}
                    </>
                ) : null}
            </section>

            {user?.role === 'admin' ? (
                <section className="card">
                    <div className="card-header">
                        <div>
                            <h2 className="card-title">用户管理</h2>
                        </div>
                        <button type="button" className="btn-primary" onClick={() => setShowAddUser((current) => !current)}>
                            {showAddUser ? '收起表单' : '新增用户'}
                        </button>
                    </div>

                    {showAddUser ? (
                        <form className="card subtle-card" onSubmit={handleAddUser}>
                            <div className="field-grid three">
                                <label className="field">
                                    <span>用户名</span>
                                    <input value={newUsername} onChange={(event) => setNewUsername(event.target.value)} required />
                                </label>
                                <label className="field">
                                    <span>密码</span>
                                    <input
                                        type="password"
                                        value={newPassword}
                                        onChange={(event) => setNewPassword(event.target.value)}
                                        required
                                    />
                                </label>
                                <label className="field">
                                    <span>角色</span>
                                    <select value={newRole} onChange={(event) => setNewRole(event.target.value)}>
                                        <option value="user">普通用户</option>
                                        <option value="admin">管理员</option>
                                    </select>
                                </label>
                            </div>
                            <div className="action-row">
                                <button type="submit" className="btn-primary">
                                    创建用户
                                </button>
                                <button type="button" className="btn-secondary" onClick={() => setShowAddUser(false)}>
                                    取消
                                </button>
                            </div>
                        </form>
                    ) : null}

                    <div className="list compact-list">
                        {users.map((entry) => (
                            <div key={entry.id} className="list-row">
                                <div className="list-row-main">
                                    <div className="list-row-title">{entry.username}</div>
                                    <div className="list-row-subtitle">{formatDateTime(entry.created_at)}</div>
                                </div>
                                <div className="list-row-meta">
                                    <span className="status-tag is-info">{entry.role === 'admin' ? '管理员' : '普通用户'}</span>
                                    {entry.username !== 'admin' ? (
                                        <button
                                            type="button"
                                            className="btn-ghost danger"
                                            onClick={() => handleDeleteUser(entry.id)}
                                        >
                                            删除
                                        </button>
                                    ) : (
                                        <span className="page-chip">默认管理员</span>
                                    )}
                                </div>
                            </div>
                        ))}
                        {!users.length ? <div className="empty-state">暂无用户。</div> : null}
                    </div>
                </section>
            ) : null}
        </div>
    );
}

export default Settings;
