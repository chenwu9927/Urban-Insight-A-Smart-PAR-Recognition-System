import { useState } from 'react';
import { AlertCircle, Lock, LogIn, ShieldCheck, User } from 'lucide-react';
import { api } from '../lib/api';

const Login = ({ onLogin }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (event) => {
        event.preventDefault();
        setError('');
        setLoading(true);

        try {
            const response = await api.post('/auth/login', { username, password });
            if (response.data.ok) {
                localStorage.setItem('user', JSON.stringify(response.data.user));
                localStorage.setItem('token', response.data.user.id.toString());
                onLogin(response.data.user);
            }
        } catch (err) {
            setError(err.response?.data?.detail || '登录失败，请检查用户名和密码。');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="auth-shell">
            <div className="auth-card">
                <div className="auth-header">
                    <div className="auth-icon">
                        <ShieldCheck size={30} />
                    </div>
                    <div>
                        <span className="auth-caption">城市洞察</span>
                        <h1>登录工作台</h1>
                        <p>登录后可以访问文件库、检索、客流分析、洞察简报和常驻智能体。</p>
                    </div>
                </div>

                <form className="auth-form" onSubmit={handleSubmit}>
                    {error ? (
                        <div className="notice error">
                            <AlertCircle size={16} />
                            <span>{error}</span>
                        </div>
                    ) : null}

                    <label className="field">
                        <span>用户名</span>
                        <div className="input-wrap">
                            <User size={16} />
                            <input
                                type="text"
                                value={username}
                                onChange={(event) => setUsername(event.target.value)}
                                placeholder="请输入用户名"
                                required
                            />
                        </div>
                    </label>

                    <label className="field">
                        <span>密码</span>
                        <div className="input-wrap">
                            <Lock size={16} />
                            <input
                                type="password"
                                value={password}
                                onChange={(event) => setPassword(event.target.value)}
                                placeholder="请输入密码"
                                required
                            />
                        </div>
                    </label>

                    <button type="submit" className="btn-primary auth-submit" disabled={loading}>
                        <LogIn size={16} />
                        {loading ? '登录中...' : '登录'}
                    </button>
                </form>
            </div>
        </div>
    );
};

export default Login;
