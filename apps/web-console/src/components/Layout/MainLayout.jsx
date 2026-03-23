import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { RadioTower, Settings } from 'lucide-react';
import Sidebar from './Sidebar';

const pageMeta = [
    { match: /^\/$/, title: '工作台', subtitle: '查看系统概况、今日简报和运行状态。' },
    { match: /^\/files/, title: '文件库', subtitle: '上传媒体、发起分析、管理文件。' },
    { match: /^\/retrieval/, title: '检索', subtitle: '按条件、自然语言或图片查找目标。' },
    { match: /^\/traffic/, title: '客流分析', subtitle: '查看时段趋势和人群结构。' },
    { match: /^\/insights/, title: '洞察简报', subtitle: '生成摘要并继续提问。' },
    { match: /^\/agent/, title: '智能体', subtitle: '对话、查看运行状态、处理审批和巡检。' },
    { match: /^\/history/, title: '历史记录', subtitle: '回看分析记录和报告。' },
    { match: /^\/settings/, title: '系统设置', subtitle: '管理账号、模型和平台配置。' },
];

function getPageMeta(pathname) {
    return pageMeta.find((item) => item.match.test(pathname)) || pageMeta[0];
}

const MainLayout = ({ user }) => {
    const navigate = useNavigate();
    const location = useLocation();
    const { title, subtitle } = getPageMeta(location.pathname);
    const hostname = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
    const isIpMode = /^\d+\.\d+\.\d+\.\d+$/.test(hostname);

    return (
        <div className="layout-container">
            <Sidebar />
            <div className="main-content">
                <header className="top-header">
                    <div className="page-title-group">
                        <span>{isIpMode ? 'IP 测试访问' : '域名访问'}</span>
                        <h1>{title}</h1>
                        <p>{subtitle}</p>
                    </div>

                    <div className="top-header-meta">
                        <div className="session-badge">
                            <RadioTower size={16} />
                            <div>
                                <strong>{hostname}</strong>
                                <span>{isIpMode ? '当前通过服务器 IP 访问' : '当前通过正式域名访问'}</span>
                            </div>
                        </div>

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
};

export default MainLayout;
