import { useState, useEffect } from 'react';
import axios from 'axios';
import { User, LogOut, Shield, Users, Plus, Trash2, Key } from 'lucide-react';

const Settings = ({ user, onLogout }) => {
    const [users, setUsers] = useState([]);
    const [showAddUser, setShowAddUser] = useState(false);
    const [newUsername, setNewUsername] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [newRole, setNewRole] = useState('user');

    const fetchUsers = async () => {
        try {
            const res = await axios.get('http://localhost:8000/users');
            setUsers(res.data);
        } catch (err) {
            console.error(err);
        }
    };

    useEffect(() => {
        if (user?.role === 'admin') {
            fetchUsers();
        }
    }, [user]);

    const handleAddUser = async (e) => {
        e.preventDefault();
        try {
            await axios.post('http://localhost:8000/users', {
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
            await axios.delete(`http://localhost:8000/users/${id}`);
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
        </div>
    );
};

export default Settings;
