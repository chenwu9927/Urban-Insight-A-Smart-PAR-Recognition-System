import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';

function Settings({ user, onLogout }) {
    const isAdmin = user?.role === 'admin';
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
        if (!isAdmin) {
            return;
        }
        try {
            const response = await api.get('/users');
            setUsers(response.data || []);
        } catch (error) {
            console.error('Failed to load users', error);
        }
    }, [isAdmin]);

    const fetchLLMConfig = useCallback(async () => {
        if (!isAdmin) {
            setLlmConfigLoaded(true);
            return;
        }
        try {
            const response = await api.get('/settings/llm');
            setLlmApiKeySet(Boolean(response.data.api_key_set));
            setLlmApiKeyPreview(response.data.api_key_preview || '');
            setLlmConfig((current) => ({
                ...current,
                baseUrl: response.data.base_url || 'https://api.longcat.chat/openai',
                model: response.data.model || 'LongCat-Flash-Lite',
            }));
            setLlmSaveMessage(null);
        } catch (error) {
            console.error('Failed to load LLM config', error);
            setLlmSaveMessage({
                type: 'error',
                text: error.response?.data?.detail || '读取模型配置失败。',
            });
        } finally {
            setLlmConfigLoaded(true);
        }
    }, [isAdmin]);

    useEffect(() => {
        void fetchUsers();
        void fetchLLMConfig();
    }, [fetchLLMConfig, fetchUsers]);

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
            setLlmSaveMessage({
                type: 'error',
                text: error.response?.data?.detail || '模型配置保存失败。',
            });
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
            setLlmTestResult({
                success: false,
                message: error.response?.data?.detail || '连接测试失败。',
            });
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
        } catch (error) {
            setLlmSaveMessage({
                type: 'error',
                text: error.response?.data?.detail || 'API Key 清空失败。',
            });
        } finally {
            setLlmSaving(false);
        }
    };

    const handleLogout = async () => {
        try {
            await api.post('/auth/logout');
        } catch (error) {
            console.error('Failed to logout cleanly', error);
        } finally {
            localStorage.removeItem('user');
            localStorage.removeItem('token');
            onLogout();
        }
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
                    <div className="list-row-title">当前账号</div>
                    <div className="list compact-list" style={{ marginTop: 12 }}>
                        <div className="list-row">
                            <div className="list-row-main">
                                <div className="list-row-title">{user?.username}</div>
                                <div className="list-row-subtitle">当前登录账号</div>
                            </div>
                            <div className="list-row-meta">
                                <span className="status-tag is-info">{isAdmin ? '管理员' : '普通用户'}</span>
                            </div>
                        </div>
                    </div>
                </section>

                <section className="card">
                    <div className="list-row-title">模型状态</div>
                    {isAdmin ? (
                        <div className="list compact-list" style={{ marginTop: 12 }}>
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
                    ) : (
                        <div className="empty-state">仅管理员可以查看模型配置。</div>
                    )}
                </section>
            </div>

            {isAdmin ? (
                <>
                    <section className="card">
                        <div className="list-row-title">模型配置</div>
                        {!llmConfigLoaded ? <div className="empty-state">正在加载…</div> : null}
                        {llmConfigLoaded ? (
                            <>
                                <div className="field-grid three" style={{ marginTop: 12 }}>
                                    <label className="field">
                                        <span>API Key</span>
                                        <input
                                            type="password"
                                            value={llmConfig.apiKey}
                                            onChange={(event) =>
                                                setLlmConfig((current) => ({ ...current, apiKey: event.target.value }))
                                            }
                                            placeholder={llmApiKeySet ? `当前：${llmApiKeyPreview}` : '请输入新的 API Key'}
                                        />
                                    </label>
                                    <label className="field">
                                        <span>Base URL</span>
                                        <input
                                            type="text"
                                            value={llmConfig.baseUrl}
                                            onChange={(event) =>
                                                setLlmConfig((current) => ({ ...current, baseUrl: event.target.value }))
                                            }
                                        />
                                    </label>
                                    <label className="field">
                                        <span>模型名称</span>
                                        <input
                                            type="text"
                                            value={llmConfig.model}
                                            onChange={(event) =>
                                                setLlmConfig((current) => ({ ...current, model: event.target.value }))
                                            }
                                        />
                                    </label>
                                </div>

                                <div className="action-row" style={{ marginTop: 16 }}>
                                    <button type="button" className="btn-primary" onClick={handleSaveLLMConfig} disabled={llmSaving}>
                                        {llmSaving ? '保存中…' : '保存配置'}
                                    </button>
                                    <button type="button" className="btn-ghost" onClick={handleTestLLMConnection} disabled={llmTesting}>
                                        {llmTesting ? '测试中…' : '测试连接'}
                                    </button>
                                    {llmApiKeySet ? (
                                        <button type="button" className="btn-ghost danger" onClick={handleClearLLMKey} disabled={llmSaving}>
                                            清空 Key
                                        </button>
                                    ) : null}
                                </div>

                                {llmSaveMessage ? <div className={`notice ${llmSaveMessage.type}`}>{llmSaveMessage.text}</div> : null}
                                {llmTestResult ? (
                                    <div className={`notice ${llmTestResult.success ? 'success' : 'error'}`}>
                                        {llmTestResult.message || (llmTestResult.success ? '连接成功。' : '连接失败。')}
                                    </div>
                                ) : null}
                            </>
                        ) : null}
                    </section>

                    <section className="card">
                        <div className="card-title-row">
                            <div className="list-row-title">用户管理</div>
                            <button type="button" className="btn-ghost" onClick={() => setShowAddUser((current) => !current)}>
                                {showAddUser ? '收起' : '新增用户'}
                            </button>
                        </div>

                        {showAddUser ? (
                            <form className="field-grid three" style={{ marginTop: 12 }} onSubmit={handleAddUser}>
                                <label className="field">
                                    <span>用户名</span>
                                    <input value={newUsername} onChange={(event) => setNewUsername(event.target.value)} required />
                                </label>
                                <label className="field">
                                    <span>密码</span>
                                    <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required />
                                </label>
                                <label className="field">
                                    <span>角色</span>
                                    <select value={newRole} onChange={(event) => setNewRole(event.target.value)}>
                                        <option value="user">普通用户</option>
                                        <option value="admin">管理员</option>
                                    </select>
                                </label>
                                <div className="action-row">
                                    <button type="submit" className="btn-primary">
                                        创建用户
                                    </button>
                                </div>
                            </form>
                        ) : null}

                        <div className="list compact-list" style={{ marginTop: 12 }}>
                            {users.map((item) => (
                                <div key={item.id} className="list-row">
                                    <div className="list-row-main">
                                        <div className="list-row-title">{item.username}</div>
                                        <div className="list-row-subtitle">角色：{item.role === 'admin' ? '管理员' : '普通用户'}</div>
                                    </div>
                                    <div className="list-row-meta">
                                        {item.username !== user?.username ? (
                                            <button type="button" className="btn-ghost danger" onClick={() => handleDeleteUser(item.id)}>
                                                删除
                                            </button>
                                        ) : (
                                            <span className="status-tag is-info">当前账号</span>
                                        )}
                                    </div>
                                </div>
                            ))}
                            {!users.length ? <div className="empty-state">暂无用户。</div> : null}
                        </div>
                    </section>
                </>
            ) : null}
        </div>
    );
}

export default Settings;
