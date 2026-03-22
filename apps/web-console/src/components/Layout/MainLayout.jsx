import { Outlet, useNavigate } from 'react-router-dom';
import { Settings } from 'lucide-react';
import Sidebar from './Sidebar';

const MainLayout = ({ user }) => {
    const navigate = useNavigate();

    return (
        <div className="layout-container">
            <Sidebar />
            <div className="main-content">
                <header className="top-header">
                    <h2 style={{ fontSize: '1.25rem', fontWeight: 600, margin: 0 }}>Operations Console</h2>
                    <button
                        type="button"
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '1rem',
                            cursor: 'pointer',
                            border: 'none',
                            background: 'transparent',
                            padding: 0,
                        }}
                        onClick={() => navigate('/settings')}
                        title="Open settings"
                    >
                        <div
                            style={{
                                width: '32px',
                                height: '32px',
                                borderRadius: '50%',
                                background: 'linear-gradient(135deg, #0f766e 0%, #2563eb 100%)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: 'white',
                                fontWeight: 600,
                                fontSize: '0.9rem',
                            }}
                        >
                            {user?.username?.charAt(0).toUpperCase() || 'U'}
                        </div>
                        <span style={{ fontSize: '0.9rem', fontWeight: 500, color: '#0f172a' }}>
                            {user?.username || 'User'}
                        </span>
                        <Settings size={16} color="#64748b" />
                    </button>
                </header>
                <main className="page-content">
                    <Outlet />
                </main>
            </div>
        </div>
    );
};

export default MainLayout;
