import React from 'react';
import { useAuth } from '../hooks/useAuth';
import './Header.css';

export default function Header({ onToggleSidebar }) {
  const { username } = useAuth();

  return (
    <header className="top-header">
      <div className="header-left">
        <button 
          className="menu-toggle-btn" 
          onClick={onToggleSidebar}
          aria-label="Toggle navigation menu"
        >
          ☰
        </button>
        <div className="header-title">
          <h1>Admin Control Center</h1>
        </div>
      </div>

      <div className="header-right">
        <div className="system-status-badge">
          <span className="status-dot"></span>
          <span>System Online</span>
        </div>
        <div className="user-profile-badge">
          <span className="user-avatar">👤</span>
          <span className="user-name">{username || 'Admin'}</span>
        </div>
      </div>
    </header>
  );
}
