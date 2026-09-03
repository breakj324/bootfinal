import React from 'react';
import './RecentRequestsTable.css';

export default function RecentRequestsTable({ requests = [], onAccept, onReject }) {
  if (!requests.length) {
    return (
      <div className="requests-table-wrapper empty">
        <p>No recent requests found.</p>
      </div>
    );
  }

  const getStatusBadge = (status) => {
    switch (status.toLowerCase()) {
      case 'pending':
        return <span className="badge badge-warning">⏳ PENDING</span>;
      case 'accepted':
      case 'approved':
        return <span className="badge badge-success">✅ ACCEPTED</span>;
      case 'rejected':
        return <span className="badge badge-danger">❌ REJECTED</span>;
      default:
        return <span className="badge">{status.toUpperCase()}</span>;
    }
  };

  return (
    <div className="requests-table-container">
      <div className="table-responsive">
        <table className="requests-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Customer</th>
              <th>Promo Code</th>
              <th>Site ID</th>
              <th>Status</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {requests.map((req) => (
              <tr key={req.id}>
                <td className="cell-id">#{req.id}</td>
                <td className="cell-customer">
                  <div className="customer-info">
                    <span className="customer-name">{req.customer || req.first_name || 'User'}</span>
                    <span className="customer-uname">{req.username || '-'}</span>
                  </div>
                </td>
                <td className="cell-promo">
                  <span className="code-tag">{req.promo_code}</span>
                </td>
                <td className="cell-site-id font-mono">{req.site_id}</td>
                <td>{getStatusBadge(req.status)}</td>
                <td className="cell-date">{req.created_at}</td>
                <td className="cell-actions">
                  {req.status === 'pending' ? (
                    <div className="action-buttons">
                      <button
                        className="btn-action btn-accept"
                        title="Accept Request"
                        onClick={() => onAccept && onAccept(req.id)}
                      >
                        ✓
                      </button>
                      <button
                        className="btn-action btn-reject"
                        title="Reject Request"
                        onClick={() => onReject && onReject(req.id)}
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <span className="action-completed">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
