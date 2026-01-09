import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/Layout/MainLayout';
import Dashboard from './pages/Dashboard';
import History from './pages/History';
import Retrieval from './pages/Retrieval';
import FileLibrary from './pages/FileLibrary';
import TrafficAnalysis from './pages/TrafficAnalysis';
import Login from './pages/Login';
import Settings from './pages/Settings';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 从 localStorage 恢复登录状态
    const savedUser = localStorage.getItem('user');
    if (savedUser) {
      try {
        setUser(JSON.parse(savedUser));
      } catch (e) {
        localStorage.removeItem('user');
      }
    }
    setLoading(false);
  }, []);

  const handleLogin = (userData) => {
    setUser(userData);
  };

  const handleLogout = () => {
    setUser(null);
  };

  if (loading) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f8fafc'
      }}>
        加载中...
      </div>
    );
  }

  // 未登录显示登录页面
  if (!user) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout user={user} onLogout={handleLogout} />}>
          <Route index element={<Dashboard />} />
          <Route path="files" element={<FileLibrary />} />
          <Route path="retrieval" element={<Retrieval />} />
          <Route path="traffic" element={<TrafficAnalysis />} />
          <Route path="history" element={<History />} />
          <Route path="settings" element={<Settings user={user} onLogout={handleLogout} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;

