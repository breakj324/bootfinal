import React, { useState, useEffect, useCallback } from 'react';
import { getPendingRequests, getRequest, acceptRequest, rejectRequest } from '../services/api';

const PAGE_SIZE = 10;

/**
 * Returns a tg://openmessage deep link using the always-present telegram_user_id.
 * This opens the admin's Telegram client pointed at that user's account.
 * NOTE: This does NOT open the Bot↔Client conversation history —
 *       that must be reviewed via the Telegram Admin Bot (/admin → Requests).
 * Falls back to null if telegram_user_id is not a valid positive integer.
 */
function getTelegramDeepLink(telegramUserId) {
  if (!telegramUserId) return null;
  const uid = parseInt(telegramUserId, 10);
  if (!Number.isFinite(uid) || uid <= 0) return null;
  return `tg://openmessage?user_id=${uid}`;
}

export default function PendingRequests() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);

  // Detail Modal state
  const [selectedReq, setSelectedReq] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getPendingRequests({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setRequests(data || []);
    } catch (err) {
      console.error('Failed to load pending requests:', err);
      setError(err.message || 'تعذر تحميل البيانات.');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleOpenDetail = async (id) => {
    try {
      setLoadingDetail(true);
      setActionMessage(null);
      const detail = await getRequest(id);
      setSelectedReq(detail);
    } catch (err) {
      setActionMessage({ type: 'error', text: err.message });
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleAction = async (id, action) => {
    try {
      setActionMessage(null);
      if (action === 'accept') {
        await acceptRequest(id);
        setActionMessage({ type: 'success', text: `✅ تم قبول الطلب #${id} بنجاح.` });
      } else {
        await rejectRequest(id);
        setActionMessage({ type: 'success', text: `✅ تم رفض الطلب #${id} بنجاح.` });
      }
      setSelectedReq(null);
      // Remove processed request immediately and refresh list
      setRequests((prev) => prev.filter((r) => r.id !== id));
      await loadData();
    } catch (err) {
      setActionMessage({ type: 'error', text: err.message });
    }
  };

  if (loading && requests.length === 0) {
    return (
      <div className="overview-loading">
        <div className="loading-spinner"></div>
        <span>جاري التحميل...</span>
      </div>
    );
  }

  if (error && requests.length === 0) {
    return (
      <div className="overview-error">
        <span className="error-icon">⚠️</span>
        <h3>تعذر تحميل البيانات</h3>
        <p>{error}</p>
        <button className="btn-retry" onClick={loadData}>
          🔄 إعادة المحاولة
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>📥 Pending Requests</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginTop: '2px' }}>
            مراجعة طلبات المستخدمين والموافقة على المكافآت
          </p>
        </div>
        <button className="btn-refresh" onClick={loadData} title="تحديث">
          🔄 تحديث
        </button>
      </div>

      {actionMessage && (
        <div className={`action-alert ${actionMessage.type}`}>
          <span>{actionMessage.text}</span>
          <button className="alert-close" onClick={() => setActionMessage(null)}>×</button>
        </div>
      )}

      {/* Requests Table */}
      <div className="requests-table-container">
        <div className="table-responsive">
          <table className="requests-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Customer</th>
                <th>Promo Code</th>
                <th>Site ID</th>
                <th>Screenshot</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {requests.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center', padding: 'var(--space-xl)', color: 'var(--text-muted)' }}>
                    📭 لا توجد طلبات معلقة حالياً
                  </td>
                </tr>
              ) : (
                requests.map((r) => (
                  <tr key={r.id}>
                    <td className="cell-id">#{r.id}</td>
                    <td className="cell-customer">
                      <div className="customer-info">
                        <span className="customer-name">{r.first_name || 'Customer'}</span>
                        <span className="customer-uname">{r.username ? `@${r.username}` : '-'}</span>
                      </div>
                    </td>
                    <td>
                      <span className="code-tag">{r.promo_code}</span>
                    </td>
                    <td className="font-mono">{r.site_id || '—'}</td>
                    <td>
                      {r.has_screenshot ? (
                        <span style={{ color: 'var(--color-info)', fontSize: '0.85rem' }}>📷 متاح</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>—</span>
                      )}
                    </td>
                    <td>
                      <span className="badge badge-warning">⏳ PENDING</span>
                    </td>
                    <td className="cell-date">{(r.created_at || '').substring(0, 10)}</td>
                    <td>
                      <div className="action-buttons">
                        <button
                          className="btn-refresh"
                          style={{ padding: '4px 10px', fontSize: '0.8rem' }}
                          onClick={() => handleOpenDetail(r.id)}
                          title="عرض التفاصيل"
                        >
                          📄 فتح
                        </button>
                        <button
                          className="btn-action btn-accept"
                          onClick={() => handleAction(r.id, 'accept')}
                          title="قبول الطلب"
                        >
                          ✓
                        </button>
                        <button
                          className="btn-action btn-reject"
                          onClick={() => handleAction(r.id, 'reject')}
                          title="رفض الطلب"
                        >
                          ✕
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'var(--space-xs)' }}>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          صفحة {page + 1}
        </span>
        <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
          <button
            className="btn-refresh"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            style={{ opacity: page === 0 ? 0.5 : 1 }}
          >
            ⬅️ السابق
          </button>
          <button
            className="btn-refresh"
            disabled={requests.length < PAGE_SIZE}
            onClick={() => setPage((p) => p + 1)}
            style={{ opacity: requests.length < PAGE_SIZE ? 0.5 : 1 }}
          >
            ➡️ التالي
          </button>
        </div>
      </div>

      {/* Request Detail Modal */}
      {selectedReq && (
        <div className="modal-backdrop" onClick={() => setSelectedReq(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>📥 تفاصيل الطلب #{selectedReq.id}</h3>
              <button className="modal-close-btn" onClick={() => setSelectedReq(null)}>×</button>
            </div>

            <div className="modal-body">
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-label">المشترك</span>
                  <span className="detail-val">{selectedReq.first_name || '—'}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Username</span>
                  <span className="detail-val">{selectedReq.username ? `@${selectedReq.username}` : '—'}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Telegram User ID</span>
                  <span className="detail-val font-mono">{selectedReq.telegram_user_id}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Promo Code</span>
                  <span className="detail-val">
                    <span className="code-tag">{selectedReq.promo_code}</span>
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Site ID</span>
                  <span className="detail-val font-mono">{selectedReq.site_id || '—'}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">الحالة</span>
                  <span className="detail-val">
                    <span className="badge badge-warning">{selectedReq.status.toUpperCase()}</span>
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">تاريخ الإنشاء</span>
                  <span className="detail-val">{selectedReq.created_at}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">الإثبات المرفق</span>
                  <span className="detail-val" style={{ color: 'var(--color-info)' }}>
                    {selectedReq.has_screenshot
                      ? 'Media proof available through Telegram'
                      : 'لا يوجد إثبات'}
                  </span>
                </div>
              </div>

              {/* Telegram Conversation Action */}
              <div style={{ marginTop: 'var(--space-md)', paddingTop: 'var(--space-sm)', borderTop: '1px solid var(--color-border)' }}>
                {getTelegramDeepLink(selectedReq.telegram_user_id) ? (
                  <>
                    <a
                      href={getTelegramDeepLink(selectedReq.telegram_user_id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-refresh"
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        textDecoration: 'none',
                        background: 'var(--color-primary, #0088cc)',
                        color: '#ffffff',
                        fontWeight: 600,
                        width: '100%',
                        padding: '10px 16px',
                        borderRadius: 'var(--radius-md)',
                        textAlign: 'center',
                      }}
                    >
                      💬 Open Telegram Conversation
                    </a>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '6px', lineHeight: 1.4 }}>
                      ⓘ To review the submitted proof (photo/video), open the <strong>Telegram Admin Bot</strong> and navigate to Requests → #{selectedReq.id}.
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center', padding: '6px' }}>
                    Telegram user ID unavailable for this request.
                  </div>
                )}
              </div>

            </div>

            <div className="modal-footer">
              <button
                className="btn-retry"
                style={{ background: 'var(--color-success)' }}
                onClick={() => handleAction(selectedReq.id, 'accept')}
              >
                ✅ قبول الطلب
              </button>
              <button
                className="btn-retry"
                style={{ background: 'var(--color-danger)' }}
                onClick={() => handleAction(selectedReq.id, 'reject')}
              >
                ❌ رفض الطلب
              </button>
              <button
                className="btn-refresh"
                onClick={() => setSelectedReq(null)}
              >
                إغلاق
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
