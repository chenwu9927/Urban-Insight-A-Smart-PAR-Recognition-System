import { NavLink } from 'react-router-dom';
import {
    BarChart3,
    Bot,
    FolderOpen,
    History,
    LayoutDashboard,
    Search,
    Settings,
    Sparkles,
} from 'lucide-react';

const navItemClass = ({ isActive }) => `nav-item ${isActive ? 'active' : ''}`;

const items = [
    { to: '/', label: '总览', icon: LayoutDashboard },
    { to: '/files', label: '任务', icon: FolderOpen },
    { to: '/retrieval', label: '检索', icon: Search },
    { to: '/insights', label: '研判', icon: Sparkles },
    { to: '/agent', label: '智能体', icon: Bot },
    { to: '/traffic', label: '趋势', icon: BarChart3 },
    { to: '/history', label: '记录', icon: History },
];

function Sidebar() {
    return (
        <aside className="sidebar">
            <div className="sidebar-brand minimal">
                <div className="sidebar-brand-mark">CI</div>
                <div>
                    <h1>城市洞察</h1>
                </div>
            </div>

            <nav className="sidebar-nav compact">
                {items.map((item) => {
                    const Icon = item.icon;
                    return (
                        <NavLink key={item.to} to={item.to} className={navItemClass}>
                            <Icon size={18} />
                            <span>{item.label}</span>
                        </NavLink>
                    );
                })}
            </nav>

            <div className="sidebar-footer">
                <NavLink to="/settings" className={navItemClass}>
                    <Settings size={18} />
                    <span>设置</span>
                </NavLink>
            </div>
        </aside>
    );
}

export default Sidebar;
