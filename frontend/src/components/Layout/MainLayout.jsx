import { Outlet, useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import { Settings } from 'lucide-react';

const MainLayout = ({ user, onLogout }) => {
    const navigate = useNavigate();

    return (
        <div className="layout-container">
            <Sidebar />
            <div className="main-content">
                <header className="top-header">
                    <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>控制台</h2>
                    <div
                        style={{ display: 'flex', alignItems: 'center', gap: '1rem', cursor: 'pointer' }}
                        onClick={() => navigate('/settings')}
                        title="点击进入设置"
                    >
                        <div style={{
                            width: '32px',
                            height: '32px',
                            borderRadius: '50%',
                            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: 'white',
                            fontWeight: 600,
                            fontSize: '0.9rem'
                        }}>
                            {user?.username?.charAt(0).toUpperCase() || 'U'}
                        </div>
                        <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>{user?.username || '用户'}</span>
                        <Settings size={16} color="#64748b" />
                    </div>
                </header>
                <main className="page-content">
                    <Outlet />
                </main>
            </div>
        </div>
    );
};

export default MainLayout;

