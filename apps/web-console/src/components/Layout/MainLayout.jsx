import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { RadioTower, Settings } from 'lucide-react';
import Sidebar from './Sidebar';

const pageMeta = [
    { match: /^\/$/, title: 'Client Workspace', subtitle: 'A single operational surface for evidence, analysis, and automation.' },
    { match: /^\/files/, title: 'Evidence Library', subtitle: 'Manage uploaded media and prepare new material for analysis.' },
    { match: /^\/retrieval/, title: 'Smart Retrieval', subtitle: 'Find people, events, and matches across processed material.' },
    { match: /^\/traffic/, title: 'Flow Analytics', subtitle: 'Review movement volume, peaks, and temporal changes.' },
    { match: /^\/insights/, title: 'Insight Briefs', subtitle: 'Read generated summaries, alerts, and analysis commentary.' },
    { match: /^\/agent/, title: 'Agent Center', subtitle: 'Assign tasks, inspect runtime state, and follow agent activity.' },
    { match: /^\/history/, title: 'Operations Log', subtitle: 'Trace execution history, sessions, and operational changes.' },
    { match: /^\/settings/, title: 'Platform Settings', subtitle: 'Control credentials, integrations, and access preferences.' },
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
                <header className="top-header client-header">
                    <div>
                        <div className="client-header-eyebrow">{isIpMode ? 'IP test session' : 'Domain session'}</div>
                        <h2 className="client-header-title">{title}</h2>
                        <p className="client-header-subtitle">{subtitle}</p>
                    </div>

                    <div className="client-header-actions">
                        <div className="client-connection-chip">
                            <RadioTower size={16} />
                            <span>{hostname}</span>
                        </div>

                        <button
                            type="button"
                            className="client-user-button"
                            onClick={() => navigate('/settings')}
                            title="Open settings"
                        >
                            <div className="client-user-avatar">{user?.username?.charAt(0).toUpperCase() || 'U'}</div>
                            <div className="client-user-text">
                                <strong>{user?.username || 'User'}</strong>
                                <span>Workspace profile</span>
                            </div>
                            <Settings size={16} color="#64748b" />
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
