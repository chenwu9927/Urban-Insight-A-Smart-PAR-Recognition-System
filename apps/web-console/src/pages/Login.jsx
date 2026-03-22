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
            setError(err.response?.data?.detail || 'Login failed. Please verify your credentials and try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="auth-shell">
            <div className="auth-panel">
                <div className="auth-brand">
                    <div className="auth-brand-icon">
                        <ShieldCheck size={36} />
                    </div>
                    <div>
                        <span className="auth-eyebrow">Urban Insight Client</span>
                        <h1>Sign in to the operations workspace.</h1>
                        <p>
                            Access evidence management, retrieval, analytics, and the always-on agent from one secure
                            client console.
                        </p>
                    </div>
                </div>

                <div className="auth-feature-strip">
                    <div>
                        <strong>Live agent</strong>
                        <span>Monitor active runs and receive operational feedback in real time.</span>
                    </div>
                    <div>
                        <strong>Unified workflow</strong>
                        <span>Move from upload to retrieval and insight review without switching tools.</span>
                    </div>
                </div>

                <form className="auth-form" onSubmit={handleSubmit}>
                    {error ? (
                        <div className="auth-error">
                            <AlertCircle size={16} />
                            <span>{error}</span>
                        </div>
                    ) : null}

                    <label className="auth-field">
                        <span>Username</span>
                        <div className="auth-input-wrap">
                            <User size={18} />
                            <input
                                type="text"
                                value={username}
                                onChange={(event) => setUsername(event.target.value)}
                                placeholder="Enter your username"
                                required
                            />
                        </div>
                    </label>

                    <label className="auth-field">
                        <span>Password</span>
                        <div className="auth-input-wrap">
                            <Lock size={18} />
                            <input
                                type="password"
                                value={password}
                                onChange={(event) => setPassword(event.target.value)}
                                placeholder="Enter your password"
                                required
                            />
                        </div>
                    </label>

                    <button type="submit" className="auth-submit" disabled={loading}>
                        <LogIn size={18} />
                        {loading ? 'Signing in...' : 'Sign in'}
                    </button>
                </form>
            </div>
        </div>
    );
};

export default Login;
