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

const primaryItems = [
    { to: '/', label: '工作台', icon: LayoutDashboard },
    { to: '/files', label: '文件库', icon: FolderOpen },
    { to: '/retrieval', label: '检索', icon: Search },
    { to: '/traffic', label: '客流分析', icon: BarChart3 },
    { to: '/insights', label: '洞察简报', icon: Sparkles },
];

const operationsItems = [
    { to: '/agent', label: '智能体', icon: Bot },
    { to: '/history', label: '历史记录', icon: History },
];

function SidebarSection({ title, items }) {
    return (
        <div className="sidebar-section">
            <div className="sidebar-section-label">{title}</div>
            {items.map((item) => {
                const Icon = item.icon;
                return (
                    <NavLink key={item.to} to={item.to} className={navItemClass}>
                        <Icon size={18} />
                        <span>{item.label}</span>
                    </NavLink>
                );
            })}
        </div>
    );
}

const Sidebar = () => {
    return (
        <aside className="sidebar">
            <div className="sidebar-brand">
                <div className="sidebar-brand-mark">UI</div>
                <div>
                    <h1>城市洞察</h1>
                    <p>智能安防工作台</p>
                </div>
            </div>

            <div className="sidebar-note">
                <strong>统一入口</strong>
                <p>文件、分析、检索、洞察和智能体都放在同一个前端工作区内。</p>
            </div>

            <nav className="sidebar-nav">
                <SidebarSection title="业务功能" items={primaryItems} />
                <SidebarSection title="运行与协同" items={operationsItems} />
            </nav>

            <div className="sidebar-footer">
                <NavLink to="/settings" className={navItemClass}>
                    <Settings size={18} />
                    <span>系统设置</span>
                </NavLink>
            </div>
        </aside>
    );
};

export default Sidebar;
