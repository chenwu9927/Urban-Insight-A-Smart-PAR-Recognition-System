import { useCallback, useEffect, useState } from 'react';
import {
    Bot,
    CheckCircle,
    Key,
    Loader2,
    LogOut,
    Plus,
    Shield,
    Trash2,
    User,
    Users,
    XCircle,
    Zap,
} from 'lucide-react';
import { api } from '../lib/api';

const inputStyle = {
    width: '100%',
    padding: '0.75rem',
    borderRadius: '0.5rem',
    border: '1px solid #d1d5db',
    fontSize: '0.9rem',
};

const Settings = ({ user, onLogout }) => {
    const [users, setUsers] = useState([]);
    const [showAddUser, setShowAddUser] = useState(false);
    const [newUsername, setNewUsername] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [newRole, setNewRole] = useState('user');
    const [llmConfig, setLlmConfig] = useState({
        apiKey: '',
        baseUrl: 'https://api.openai.com/v1',
        model: 'gpt-4o-mini',
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
            setUsers(response.data);
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
                baseUrl: response.data.base_url || 'https://api.openai.com/v1',
                model: response.data.model || 'gpt-4o-mini',
            }));
        } catch (error) {
            console.error('Failed to load LLM config', error);
        } finally {
            setLlmConfigLoaded(true);
        }
    }, []);

    useEffect(() => {
        if (user?.role === 'admin') {
            fetchUsers();
        }
        fetchLLMConfig();
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
            fetchUsers();
        } catch (error) {
            alert(error.response?.data?.detail || 'Failed to add user.');
        }
    };

    const handleDeleteUser = async (id) => {
        if (!confirm('Delete this user?')) {
            return;
        }
        try {
            await api.delete(`/users/${id}`);
            fetchUsers();
        } catch (error) {
            alert(error.response?.data?.detail || 'Failed to delete user.');
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
                model: llmConfig.model,
            };
            if (llmConfig.apiKey) {
                payload.api_key = llmConfig.apiKey;
            }
            await api.post('/settings/llm', payload);
            setLlmSaveMessage({ type: 'success', text: 'LLM settings saved.' });
            setLlmConfig((current) => ({ ...current, apiKey: '' }));
            fetchLLMConfig();
        } catch (error) {
            setLlmSaveMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save LLM settings.' });
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
            setLlmTestResult({ success: false, message: error.response?.data?.detail || 'Connection test failed.' });
        } finally {
            setLlmTesting(false);
        }
    };

    const handleClearLLMKey = async () => {
        if (!confirm('Clear the stored API key?')) {
            return;
        }
        setLlmSaving(true);
        try {
            await api.post('/settings/llm', { api_key: '' });
            setLlmSaveMessage({ type: 'success', text: 'API key cleared.' });
            fetchLLMConfig();
        } catch {
            setLlmSaveMessage({ type: 'error', text: 'Failed to clear API key.' });
        } finally {
            setLlmSaving(false);
        }
    };

    return (
        <div>
            <h1 style={{ fontSize: '1.8rem', marginBottom: '2rem' }}>Settings</h1>

            <div className="stat-card" style={{ marginBottom: '2rem' }}>
                <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <User size={20} />
                    Current account
                </h3>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                    <div>
                        <div style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.5rem' }}>{user?.username}</div>
                        <span
                            style={{
                                background: user?.role === 'admin' ? '#dbeafe' : '#f0fdf4',
                                color: user?.role === 'admin' ? '#1d4ed8' : '#16a34a',
                                padding: '0.25rem 0.75rem',
                                borderRadius: '999px',
                                fontSize: '0.875rem',
                            }}
                        >
                            {user?.role === 'admin' ? 'Administrator' : 'Standard user'}
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
                            fontWeight: 500,
                        }}
                    >
                        <LogOut size={18} />
                        Log out
                    </button>
                </div>
            </div>

            <div className="stat-card" style={{ marginBottom: '2rem' }}>
                <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Bot size={20} />
                    LLM configuration
                    <span
                        style={{
                            marginLeft: 'auto',
                            fontSize: '0.75rem',
                            padding: '0.25rem 0.5rem',
                            borderRadius: '999px',
                            background: llmApiKeySet ? '#dcfce7' : '#fef3c7',
                            color: llmApiKeySet ? '#16a34a' : '#d97706',
                        }}
                    >
                        {llmApiKeySet ? 'Configured' : 'Missing API key'}
                    </span>
                </h3>

                <div style={{ marginBottom: '1rem', fontSize: '0.9rem', color: '#6b7280' }}>
                    Configure the LLM provider used by insight generation, reports, and future agent reasoning flows.
                </div>

                {!llmConfigLoaded ? (
                    <div style={{ textAlign: 'center', padding: '2rem', color: '#9ca3af' }}>
                        <Loader2 size={24} className="spin" />
                        <div>Loading configuration...</div>
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', fontWeight: 500 }}>
                                API key
                            </label>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                <input
                                    type="password"
                                    value={llmConfig.apiKey}
                                    onChange={(event) => setLlmConfig((current) => ({ ...current, apiKey: event.target.value }))}
                                    placeholder={llmApiKeySet ? `Current: ${llmApiKeyPreview} (enter a new value to replace it)` : 'sk-...'}
                                    style={{ ...inputStyle, flex: 1 }}
                                />
                                {llmApiKeySet ? (
                                    <button
                                        onClick={handleClearLLMKey}
                                        style={{
                                            padding: '0.75rem',
                                            background: '#fee2e2',
                                            color: '#dc2626',
                                            border: 'none',
                                            borderRadius: '0.5rem',
                                            cursor: 'pointer',
                                        }}
                                        title="Clear API key"
                                    >
                                        <Trash2 size={18} />
                                    </button>
                                ) : null}
                            </div>
                        </div>

                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', fontWeight: 500 }}>
                                API base URL
                            </label>
                            <input
                                type="text"
                                value={llmConfig.baseUrl}
                                onChange={(event) => setLlmConfig((current) => ({ ...current, baseUrl: event.target.value }))}
                                placeholder="https://api.openai.com/v1"
                                style={inputStyle}
                            />
                            <div style={{ marginTop: '0.25rem', fontSize: '0.8rem', color: '#9ca3af' }}>
                                OpenAI, DeepSeek, and other OpenAI-compatible gateways are supported.
                            </div>
                        </div>

                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', fontWeight: 500 }}>
                                Model
                            </label>
                            <input
                                type="text"
                                value={llmConfig.model}
                                onChange={(event) => setLlmConfig((current) => ({ ...current, model: event.target.value }))}
                                placeholder="gpt-4o-mini"
                                style={inputStyle}
                            />
                            <div style={{ marginTop: '0.25rem', fontSize: '0.8rem', color: '#9ca3af' }}>
                                Common models: gpt-4o-mini, gpt-4o, deepseek-chat, glm-4.
                            </div>
                        </div>

                        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                            <button
                                onClick={handleSaveLLMConfig}
                                disabled={llmSaving}
                                className="btn-primary"
                                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', opacity: llmSaving ? 0.7 : 1 }}
                            >
                                {llmSaving ? <Loader2 size={16} className="spin" /> : <Key size={16} />}
                                Save configuration
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
                                    opacity: llmTesting ? 0.7 : 1,
                                }}
                            >
                                {llmTesting ? <Loader2 size={16} className="spin" /> : <Zap size={16} />}
                                Test connection
                            </button>
                        </div>

                        {llmSaveMessage ? (
                            <div
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    padding: '0.75rem 1rem',
                                    borderRadius: '0.5rem',
                                    background: llmSaveMessage.type === 'success' ? '#dcfce7' : '#fee2e2',
                                    color: llmSaveMessage.type === 'success' ? '#16a34a' : '#dc2626',
                                }}
                            >
                                {llmSaveMessage.type === 'success' ? <CheckCircle size={18} /> : <XCircle size={18} />}
                                {llmSaveMessage.text}
                            </div>
                        ) : null}

                        {llmTestResult ? (
                            <div
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    padding: '0.75rem 1rem',
                                    borderRadius: '0.5rem',
                                    background: llmTestResult.success ? '#dcfce7' : '#fee2e2',
                                    color: llmTestResult.success ? '#16a34a' : '#dc2626',
                                }}
                            >
                                {llmTestResult.success ? <CheckCircle size={18} /> : <XCircle size={18} />}
                                {llmTestResult.message}
                            </div>
                        ) : null}
                    </div>
                )}
            </div>

            {user?.role === 'admin' ? (
                <div className="stat-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', gap: '1rem', flexWrap: 'wrap' }}>
                        <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Users size={20} />
                            User management
                        </h3>
                        <button className="btn-primary" onClick={() => setShowAddUser(true)} style={{ padding: '0.5rem 1rem' }}>
                            <Plus size={16} />
                            Add user
                        </button>
                    </div>

                    {showAddUser ? (
                        <form
                            onSubmit={handleAddUser}
                            style={{ background: '#f8fafc', padding: '1.5rem', borderRadius: '0.5rem', marginBottom: '1.5rem' }}
                        >
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '1rem', alignItems: 'end' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem' }}>Username</label>
                                    <input value={newUsername} onChange={(event) => setNewUsername(event.target.value)} style={inputStyle} required />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem' }}>Password</label>
                                    <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} style={inputStyle} required />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem' }}>Role</label>
                                    <select value={newRole} onChange={(event) => setNewRole(event.target.value)} style={inputStyle}>
                                        <option value="user">User</option>
                                        <option value="admin">Admin</option>
                                    </select>
                                </div>
                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                    <button type="submit" className="btn-primary" style={{ padding: '0.5rem 1rem' }}>
                                        Create
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setShowAddUser(false)}
                                        style={{ padding: '0.5rem 1rem', border: '1px solid #d1d5db', borderRadius: '0.375rem', background: 'white', cursor: 'pointer' }}
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        </form>
                    ) : null}

                    <div className="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Username</th>
                                    <th>Role</th>
                                    <th>Created at</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users.map((entry) => (
                                    <tr key={entry.id}>
                                        <td>#{entry.id}</td>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                {entry.role === 'admin' ? <Shield size={14} color="#1d4ed8" /> : null}
                                                {entry.username}
                                            </div>
                                        </td>
                                        <td>
                                            <span
                                                style={{
                                                    background: entry.role === 'admin' ? '#dbeafe' : '#f0fdf4',
                                                    color: entry.role === 'admin' ? '#1d4ed8' : '#16a34a',
                                                    padding: '0.2rem 0.5rem',
                                                    borderRadius: '999px',
                                                    fontSize: '0.8rem',
                                                }}
                                            >
                                                {entry.role === 'admin' ? 'Admin' : 'User'}
                                            </span>
                                        </td>
                                        <td>{new Date(entry.created_at).toLocaleString()}</td>
                                        <td>
                                            {entry.username !== 'admin' ? (
                                                <button
                                                    onClick={() => handleDeleteUser(entry.id)}
                                                    style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#ef4444' }}
                                                    title="Delete user"
                                                >
                                                    <Trash2 size={16} />
                                                </button>
                                            ) : null}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            ) : null}
        </div>
    );
};

export default Settings;
