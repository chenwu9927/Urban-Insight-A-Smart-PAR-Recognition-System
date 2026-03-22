import { Suspense, lazy, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

const MainLayout = lazy(() => import('./components/Layout/MainLayout'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const History = lazy(() => import('./pages/History'));
const Retrieval = lazy(() => import('./pages/Retrieval'));
const FileLibrary = lazy(() => import('./pages/FileLibrary'));
const TrafficAnalysis = lazy(() => import('./pages/TrafficAnalysis'));
const Insights = lazy(() => import('./pages/Insights'));
const Login = lazy(() => import('./pages/Login'));
const Settings = lazy(() => import('./pages/Settings'));
const AgentOps = lazy(() => import('./pages/AgentOps'));

function loadStoredUser() {
    const raw = localStorage.getItem('user');
    if (!raw) {
        return null;
    }
    try {
        return JSON.parse(raw);
    } catch {
        localStorage.removeItem('user');
        return null;
    }
}

function AppFallback() {
    return (
        <div
            style={{
                minHeight: '100vh',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: '#f8fafc',
                color: '#475569',
                fontWeight: 600,
            }}
        >
            Loading workspace...
        </div>
    );
}

function App() {
    const [user, setUser] = useState(loadStoredUser);

    const handleLogin = (userData) => {
        setUser(userData);
    };

    const handleLogout = () => {
        setUser(null);
    };

    if (!user) {
        return (
            <Suspense fallback={<AppFallback />}>
                <Login onLogin={handleLogin} />
            </Suspense>
        );
    }

    return (
        <BrowserRouter>
            <Suspense fallback={<AppFallback />}>
                <Routes>
                    <Route path="/" element={<MainLayout user={user} />}>
                        <Route index element={<Dashboard />} />
                        <Route path="files" element={<FileLibrary />} />
                        <Route path="retrieval" element={<Retrieval />} />
                        <Route path="traffic" element={<TrafficAnalysis />} />
                        <Route path="insights" element={<Insights />} />
                        <Route path="agent" element={<AgentOps user={user} />} />
                        <Route path="history" element={<History />} />
                        <Route path="settings" element={<Settings user={user} onLogout={handleLogout} />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Route>
                </Routes>
            </Suspense>
        </BrowserRouter>
    );
}

export default App;
