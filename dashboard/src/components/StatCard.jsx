import React from 'react';
import './StatCard.css';

export default function StatCard({ title, value, icon, variant = 'default', note }) {
  return (
    <div className={`stat-card stat-card-${variant}`}>
      <div className="stat-card-header">
        <span className="stat-card-title">{title}</span>
        <span className="stat-card-icon">{icon}</span>
      </div>
      <div className="stat-card-body">
        <span className="stat-card-value">{value}</span>
      </div>
      {note && <div className="stat-card-footer">{note}</div>}
    </div>
  );
}
