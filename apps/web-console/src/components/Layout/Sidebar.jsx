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
    { to: '/', label: 'Home Workspace', icon: LayoutDashboard },
    { to: '/files', label: 'Evidence Library', icon: FolderOpen },
    { to: '/retrieval', label: 'Smart Retrieval', icon: Search },
    { to: '/traffic', label: 'Flow Analytics', icon: BarChart3 },
    { to: '/insights', label: 'Insight Briefs', icon: Sparkles },
];

const operationsItems = [
    { to: '/agent', label: 'Agent Center', icon: Bot },
    { to: '/history', label: 'Operations Log', icon: History },
];

function SidebarSection({ title, items }) {
    return (
        <div className="sidebar-section">
            <div className="sidebar-section-label">{title}</div>
            {items.map((item) => {
                const Icon = item.icon;
                return (
                    <NavLink key={item.to} to={item.to} className={navItemClass}>
                        <Icon size={20} />
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
                    <h1>Urban Insight</h1>
                    <p>Client operations console</p>
                </div>
            </div>

            <div className="sidebar-mode-card">
                <strong>Field-ready workspace</strong>
                <p>Use one client view for evidence intake, retrieval, analytics, and agent operations.</p>
            </div>

            <nav className="sidebar-nav">
                <SidebarSection title="Workspace" items={primaryItems} />
                <SidebarSection title="Automation" items={operationsItems} />
            </nav>

            <div className="sidebar-footer">
                <NavLink to="/settings" className={navItemClass}>
                    <Settings size={20} />
                    <span>Settings</span>
                </NavLink>
            </div>
        </aside>
    );
};

export default Sidebar;
