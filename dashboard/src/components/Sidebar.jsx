import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import './Sidebar.css';

export default function Sidebar({ isOpen, onClose }) {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const navItems = [
    { to: '/', label: 'Overview', icon: '📊' },
    { to: '/promo-codes', label: 'Promo Codes', icon: '🎟️' },
    { to: '/campaigns', label: 'Campaigns', icon: '🎯' },
    { to: '/pending-requests', label: 'Pending Requests', icon: '📥' },
    { to: '/customers', label: 'Customers', icon: '👥' },
    { to: '/statistics', label: 'Statistics', icon: '📈' },
  ];

  return (
    <>
      <div 
        className={`sidebar-overlay ${isOpen ? 'show' : ''}`} 
        onClick={onClose} 
      />
      <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <span className="brand-logo">🎁</span>
          <div className="brand-info">
            <span className="brand-name">Rewards Admin</span>
            <span className="brand-tag">v1.0.0</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              onClick={onClose}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="logout-btn" onClick={handleLogout}>
            <span className="nav-icon">🚪</span>
            <span className="nav-label">Logout</span>
          </button>
        </div>
      </aside>
    </>
  );
}
