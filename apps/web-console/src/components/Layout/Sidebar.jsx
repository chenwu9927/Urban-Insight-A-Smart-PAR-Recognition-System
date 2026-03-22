import { NavLink } from 'react-router-dom';
import { BarChart3, Bot, FolderOpen, History, LayoutDashboard, Search, Settings, Sparkles } from 'lucide-react';

const navItemClass = ({ isActive }) => `nav-item ${isActive ? 'active' : ''}`;

const Sidebar = () => {
    return (
        <div className="sidebar">
            <div style={{ padding: '2rem 1.5rem' }}>
                <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#2563eb', margin: 0 }}>UrbanInsight</h1>
                <p style={{ fontSize: '0.8rem', color: '#64748b', marginTop: '0.25rem' }}>
                    Smart pedestrian analysis platform
                </p>
            </div>

            <nav>
                <NavLink to="/" className={navItemClass}>
                    <LayoutDashboard size={20} />
                    <span>Dashboard</span>
                </NavLink>
                <NavLink to="/files" className={navItemClass}>
                    <FolderOpen size={20} />
                    <span>Files</span>
                </NavLink>
                <NavLink to="/retrieval" className={navItemClass}>
                    <Search size={20} />
                    <span>Retrieval</span>
                </NavLink>
                <NavLink to="/traffic" className={navItemClass}>
                    <BarChart3 size={20} />
                    <span>Traffic</span>
                </NavLink>
                <NavLink to="/insights" className={navItemClass}>
                    <Sparkles size={20} />
                    <span>Insights</span>
                </NavLink>
                <NavLink to="/agent" className={navItemClass}>
                    <Bot size={20} />
                    <span>Agent Center</span>
                </NavLink>
                <NavLink to="/history" className={navItemClass}>
                    <History size={20} />
                    <span>History</span>
                </NavLink>
            </nav>

            <div style={{ position: 'absolute', bottom: '2rem', width: '100%' }}>
                <NavLink to="/settings" className={navItemClass}>
                    <Settings size={20} />
                    <span>Settings</span>
                </NavLink>
            </div>
        </div>
    );
};

export default Sidebar;
