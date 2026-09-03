import React from 'react';
import './ActiveCampaignCard.css';

export default function ActiveCampaignCard({ campaign }) {
  if (!campaign) {
    return (
      <div className="active-camp-card empty">
        <div className="empty-camp-content">
          <span className="empty-icon">⚠️</span>
          <h3>No Active Campaign</h3>
          <p>Create and activate a campaign to start accepting customer submissions.</p>
        </div>
      </div>
    );
  }

  const {
    promo_code,
    status = 'active',
    max_requests = 0,
    pending_count = 0,
    remaining = 0,
  } = campaign;

  const percentage = max_requests > 0 
    ? Math.min(100, Math.round((pending_count / max_requests) * 100)) 
    : 0;

  return (
    <div className="active-camp-card">
      <div className="camp-card-header">
        <div className="camp-badge-group">
          <span className="camp-tag">🎯 Active Campaign</span>
          <span className={`status-pill status-${status}`}>
            <span className="dot"></span>
            {status.toUpperCase()}
          </span>
        </div>
        <div className="camp-promo-code">
          <span className="promo-label">Promo Code</span>
          <span className="promo-val">{promo_code}</span>
        </div>
      </div>

      <div className="camp-progress-section">
        <div className="progress-labels">
          <span className="progress-title">Requests Capacity</span>
          <span className="progress-counts">
            <strong>{pending_count}</strong> / {max_requests} ({percentage}%)
          </span>
        </div>
        <div className="progress-bar-track">
          <div 
            className="progress-bar-fill" 
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>

      <div className="camp-metrics-grid">
        <div className="camp-metric">
          <span className="metric-label">Max Allowed</span>
          <span className="metric-val">{max_requests}</span>
        </div>
        <div className="camp-metric">
          <span className="metric-label">Pending Reviews</span>
          <span className="metric-val pending-color">{pending_count}</span>
        </div>
        <div className="camp-metric">
          <span className="metric-label">Slots Remaining</span>
          <span className="metric-val remaining-color">{remaining}</span>
        </div>
      </div>
    </div>
  );
}
