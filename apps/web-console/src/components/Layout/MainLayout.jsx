import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Settings } from 'lucide-react';
import Sidebar from './Sidebar';

const pageMeta = [
    { match: /^\/$/, title: '监控总览' },
    { match: /^\/files/, title: '任务中心' },
    { match: /^\/tasks\//, title: '任务详情' },
    { match: /^\/retrieval/, title: '事件检索' },
    { match: /^\/traffic/, title: '客流趋势' },
    { match: /^\/insights/, title: '智能研判' },
    { match: /^\/agent/, title: '智能体' },
    { match: /^\/history/, title: '分析记录' },
    { match: /^\/settings/, title: '系统设置' },
];

function getPageMeta(pathname) {
    return pageMeta.find((item) => item.match.test(pathname)) || pageMeta[0];
}

function MainLayout({ user }) {
    const navigate = useNavigate();
    const location = useLocation();
    const { title } = getPageMeta(location.pathname);

    return (
        <div className="layout-container">
            <Sidebar />
            <div className="main-content">
                <header className="top-header">
                    <div className="page-title-group compact">
                        <h1>{title}</h1>
                    </div>

                    <div className="top-header-meta">
                        <button
                            type="button"
                            className="user-chip"
                            onClick={() => navigate('/settings')}
                            title="打开设置"
                        >
                            <div className="user-avatar">{user?.username?.charAt(0).toUpperCase() || 'U'}</div>
                            <div>
                                <strong>{user?.username || '用户'}</strong>
                                <span>{user?.role === 'admin' ? '管理员' : '普通用户'}</span>
                            </div>
                            <Settings size={16} />
                        </button>
                    </div>
                </header>

                <main className="page-content">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}

export default MainLayout;
