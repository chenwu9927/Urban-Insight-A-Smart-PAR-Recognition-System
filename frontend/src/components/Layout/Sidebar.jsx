import { NavLink } from 'react-router-dom';
import { LayoutDashboard, FolderOpen, History, Settings, Search, BarChart3 } from 'lucide-react';

const Sidebar = () => {
    return (
        <div className="sidebar">
            <div style={{ padding: '2rem 1.5rem' }}>
                <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#2563eb', margin: 0 }}>
                    UrbanInsight
                </h1>
                <p style={{ fontSize: '0.8rem', color: '#64748b', marginTop: '0.25rem' }}>
                    行人属性智能识别系统
                </p>
            </div>

            <nav>
                <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                    <LayoutDashboard size={20} />
                    <span>仪表盘</span>
                </NavLink>
                <NavLink to="/files" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                    <FolderOpen size={20} />
                    <span>媒体文件库</span>
                </NavLink>
                <NavLink to="/retrieval" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                    <Search size={20} />
                    <span>行人检索</span>
                </NavLink>
                <NavLink to="/traffic" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                    <BarChart3 size={20} />
                    <span>客流分析</span>
                </NavLink>
                <NavLink to="/history" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                    <History size={20} />
                    <span>处理记录</span>
                </NavLink>
            </nav>

            <div style={{ position: 'absolute', bottom: '2rem', width: '100%' }}>
                <a href="#" className="nav-item">
                    <Settings size={20} />
                    <span>系统设置</span>
                </a>
            </div>
        </div>
    );
};

export default Sidebar;
