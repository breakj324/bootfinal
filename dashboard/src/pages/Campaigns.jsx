import React, { useState, useEffect, useCallback } from 'react';
import {
  getCampaigns,
  getCampaign,
  createCampaign,
  activateCampaign,
  closeCampaign,
  getPromoCodes,
} from '../services/api';

const PAGE_SIZE = 10;

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [activePromos, setActivePromos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [actionMessage, setActionMessage] = useState(null);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [confirmActivateCamp, setConfirmActivateCamp] = useState(null);
  const [confirmCloseCamp, setConfirmCloseCamp] = useState(null);

  // Create form state
  const [createForm, setCreateForm] = useState({
    promo_code_id: '',
    max_requests: 15,
  });
  const [submittingCreate, setSubmittingCreate] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [submittingAction, setSubmittingAction] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [campsData, promosData] = await Promise.all([
        getCampaigns({
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        }),
        getPromoCodes(),
      ]);
      setCampaigns(campsData || []);
      setActivePromos((promosData || []).filter((p) => p.active === 1));
    } catch (err) {
      console.error('Failed to load campaigns:', err);
      setError(err.message || 'تعذر تحميل البيانات.');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Handle Create Submit ──────────────────────────────────────────
  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    const promoId = parseInt(createForm.promo_code_id, 10);
    const maxReqs = parseInt(createForm.max_requests, 10);

    if (!promoId) {
      setCreateError('يرجى اختيار الـ Promo Code.');
      return;
    }
    if (!maxReqs || maxReqs <= 0) {
      setCreateError('يرجى إدخال عدد أقصى صحيح أكبر من 0.');
      return;
    }

    try {
      setSubmittingCreate(true);
      setCreateError(null);

      await createCampaign({
        promo_code_id: promoId,
        max_requests: maxReqs,
      });

      setShowCreateModal(false);
      setCreateForm({ promo_code_id: '', max_requests: 15 });
      setActionMessage({
        type: 'success',
        text: 'Campaign created successfully. تم إنشاء الحملة بنجاح بحالة (CLOSED).',
      });
      await loadData();
    } catch (err) {
      setCreateError(err.message || 'فشل إنشاء الحملة.');
    } finally {
      setSubmittingCreate(false);
    }
  };

  // ── Handle Activate Execute ───────────────────────────────────────
  const handleActivateExecute = async () => {
    if (!confirmActivateCamp) return;
    try {
      setSubmittingAction(true);
      setActionMessage(null);
      await activateCampaign(confirmActivateCamp.id);
      setActionMessage({
        type: 'success',
        text: `🟢 تم تفعيل الحملة #${confirmActivateCamp.id} (${confirmActivateCamp.promo_code}) بنجاح. البوت الآن يستقبل الطلبات.`,
      });
      setConfirmActivateCamp(null);
      await loadData();
    } catch (err) {
      setActionMessage({ type: 'error', text: `❌ ${err.message}` });
      setConfirmActivateCamp(null);
    } finally {
      setSubmittingAction(false);
    }
  };

  // ── Handle Close Execute ──────────────────────────────────────────
  const handleCloseExecute = async () => {
    if (!confirmCloseCamp) return;
    try {
      setSubmittingAction(true);
      setActionMessage(null);
      await closeCampaign(confirmCloseCamp.id);
      setActionMessage({
        type: 'success',
        text: `🔴 تم إغلاق الحملة #${confirmCloseCamp.id} (${confirmCloseCamp.promo_code}) بنجاح.`,
      });
      setConfirmCloseCamp(null);
      await loadData();
    } catch (err) {
      setActionMessage({ type: 'error', text: `❌ ${err.message}` });
      setConfirmCloseCamp(null);
    } finally {
      setSubmittingAction(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status.toLowerCase()) {
      case 'active':
        return <span className="badge badge-success">🟢 ACTIVE</span>;
      case 'closed':
        return <span className="badge badge-danger">🔴 CLOSED</span>;
      case 'full':
        return <span className="badge badge-warning">🟡 FULL</span>;
      case 'completed':
        return <span className="badge badge-info">✅ COMPLETED</span>;
      default:
        return <span className="badge">{status.toUpperCase()}</span>;
    }
  };

  if (loading && campaigns.length === 0) {
    return (
      <div className="overview-loading">
        <div className="loading-spinner"></div>
        <span>جاري التحميل...</span>
      </div>
    );
  }

  if (error && campaigns.length === 0) {
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
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-md)' }}>
        <div>
          <h2>🎯 Campaigns Management</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginTop: '2px' }}>
            إدارة فترات العروض الترويجية والتحكم في حالات التفعيل والإغلاق
          </p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
          <button
            className="btn-retry"
            style={{ margin: 0, padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '6px' }}
            onClick={() => {
              setCreateError(null);
              setShowCreateModal(true);
            }}
          >
            ➕ Create Campaign
          </button>
          <button className="btn-refresh" onClick={loadData} title="تحديث">
            🔄 تحديث
          </button>
        </div>
      </div>

      {actionMessage && (
        <div className={`action-alert ${actionMessage.type}`}>
          <span>{actionMessage.text}</span>
          <button className="alert-close" onClick={() => setActionMessage(null)}>×</button>
        </div>
      )}

      {/* Campaigns Table */}
      <div className="requests-table-container">
        <div className="table-responsive">
          <table className="requests-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Promo Code</th>
                <th>Status</th>
                <th>Capacity / Progress</th>
                <th>Remaining</th>
                <th>Created</th>
                <th>Closed</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center', padding: 'var(--space-xl)', color: 'var(--text-muted)' }}>
                    لا توجد حملات مسجلة حالياً
                  </td>
                </tr>
              ) : (
                campaigns.map((c) => {
                  const pct = c.max_requests > 0
                    ? Math.min(100, Math.round((c.pending_requests / c.max_requests) * 100))
                    : 0;

                  return (
                    <tr key={c.id}>
                      <td className="cell-id">#{c.id}</td>
                      <td>
                        <span className="code-tag">{c.promo_code}</span>
                      </td>
                      <td>{getStatusBadge(c.status)}</td>
                      <td style={{ minWidth: '160px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '3px' }}>
                          <span><strong>{c.pending_requests}</strong> / {c.max_requests}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{pct}%</span>
                        </div>
                        <div className="progress-bar-track" style={{ height: '5px' }}>
                          <div
                            className="progress-bar-fill"
                            style={{
                              width: `${pct}%`,
                              background: c.status === 'full'
                                ? 'var(--color-warning)'
                                : 'linear-gradient(90deg, var(--color-primary), var(--color-info))'
                            }}
                          />
                        </div>
                      </td>
                      <td style={{ color: 'var(--color-success)', fontWeight: '600' }}>
                        {c.remaining_slots}
                      </td>
                      <td className="cell-date">{(c.created_at || '').substring(0, 10)}</td>
                      <td className="cell-date">{c.closed_at ? c.closed_at.substring(0, 10) : '—'}</td>
                      <td>
                        <div className="action-buttons">
                          {c.status === 'closed' && (
                            <button
                              className="btn-action btn-accept"
                              style={{ width: 'auto', padding: '0 10px', fontSize: '0.8rem' }}
                              onClick={() => setConfirmActivateCamp(c)}
                              title="تفعيل الحملة"
                            >
                              ▶️ Activate
                            </button>
                          )}
                          {(c.status === 'active' || c.status === 'full') && (
                            <button
                              className="btn-action btn-reject"
                              style={{ width: 'auto', padding: '0 10px', fontSize: '0.8rem' }}
                              onClick={() => setConfirmCloseCamp(c)}
                              title="إغلاق الحملة"
                            >
                              ⏹️ Close
                            </button>
                          )}
                          {c.status === 'completed' && (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>مكتملة</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
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
            disabled={campaigns.length < PAGE_SIZE}
            onClick={() => setPage((p) => p + 1)}
            style={{ opacity: campaigns.length < PAGE_SIZE ? 0.5 : 1 }}
          >
            ➡️ التالي
          </button>
        </div>
      </div>

      {/* ── CREATE CAMPAIGN MODAL ───────────────────────────────── */}
      {showCreateModal && (
        <div className="modal-backdrop" onClick={() => setShowCreateModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>➕ إنشاء Campaign جديدة</h3>
              <button className="modal-close-btn" onClick={() => setShowCreateModal(false)}>×</button>
            </div>
            <form onSubmit={handleCreateSubmit}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
                {createError && (
                  <div className="action-alert error">
                    <span>{createError}</span>
                  </div>
                )}

                <div className="form-group">
                  <label htmlFor="select-promo">🎟️ Select Promo Code * (النشطة فقط)</label>
                  <select
                    id="select-promo"
                    className="form-input"
                    value={createForm.promo_code_id}
                    onChange={(e) => setCreateForm({ ...createForm, promo_code_id: e.target.value })}
                    disabled={submittingCreate}
                    required
                  >
                    <option value="">-- اختر الرمز الترويجي --</option>
                    {activePromos.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.code} {p.description ? `(${p.description})` : ''}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="camp-max">الحد الأقصى للطلبات (Maximum Requests) *</label>
                  <input
                    id="camp-max"
                    type="number"
                    min="1"
                    className="form-input"
                    placeholder="15"
                    value={createForm.max_requests}
                    onChange={(e) => setCreateForm({ ...createForm, max_requests: e.target.value })}
                    disabled={submittingCreate}
                    required
                  />
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                    الحملة سيتم إنشاؤها بحالة (CLOSED). يمكنك تفعيلها لاحقاً.
                  </span>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="submit"
                  className="btn-retry"
                  disabled={submittingCreate}
                >
                  {submittingCreate ? 'جاري الإنشاء...' : 'Create Campaign'}
                </button>
                <button
                  type="button"
                  className="btn-refresh"
                  onClick={() => setShowCreateModal(false)}
                  disabled={submittingCreate}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── ACTIVATE CONFIRMATION MODAL ─────────────────────────── */}
      {confirmActivateCamp && (
        <div className="modal-backdrop" onClick={() => setConfirmActivateCamp(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '460px' }}>
            <div className="modal-header">
              <h3>🎯 تأكيد تفعيل العرض</h3>
              <button className="modal-close-btn" onClick={() => setConfirmActivateCamp(null)}>×</button>
            </div>
            <div className="modal-body">
              <p style={{ color: 'var(--text-primary)', fontSize: '0.95rem' }}>
                واش متأكد بلي بغيتي تفتح هاد العرض؟
              </p>
              <div style={{
                background: 'var(--color-surface-2)',
                padding: 'var(--space-md)',
                borderRadius: 'var(--radius-md)',
                marginTop: 'var(--space-sm)',
                display: 'flex',
                flexDirection: 'column',
                gap: '4px',
                fontSize: '0.88rem'
              }}>
                <div><strong>Promo Code:</strong> <span className="code-tag">{confirmActivateCamp.promo_code}</span></div>
                <div><strong>Maximum Requests:</strong> {confirmActivateCamp.max_requests}</div>
                <div><strong>Campaign ID:</strong> #{confirmActivateCamp.id}</div>
              </div>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 'var(--space-sm)' }}>
                ⚠️ ملاحظة: يمكن أن يكون هناك عرض واحد فقط نشط (ACTIVE) في نفس الوقت.
              </p>
            </div>
            <div className="modal-footer">
              <button
                className="btn-retry"
                style={{ background: 'var(--color-success)' }}
                onClick={handleActivateExecute}
                disabled={submittingAction}
              >
                {submittingAction ? 'جاري التفعيل...' : '✅ تفعيل'}
              </button>
              <button
                className="btn-refresh"
                onClick={() => setConfirmActivateCamp(null)}
                disabled={submittingAction}
              >
                إلغاء
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── CLOSE CONFIRMATION MODAL ────────────────────────────── */}
      {confirmCloseCamp && (
        <div className="modal-backdrop" onClick={() => setConfirmCloseCamp(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '460px' }}>
            <div className="modal-header">
              <h3>⏹️ تأكيد إغلاق العرض</h3>
              <button className="modal-close-btn" onClick={() => setConfirmCloseCamp(null)}>×</button>
            </div>
            <div className="modal-body">
              <p style={{ color: 'var(--text-primary)', fontSize: '0.95rem' }}>
                واش متأكد بلي بغيتي تسد هاد العرض؟
              </p>
              <div style={{
                background: 'var(--color-surface-2)',
                padding: 'var(--space-md)',
                borderRadius: 'var(--radius-md)',
                marginTop: 'var(--space-sm)',
                display: 'flex',
                flexDirection: 'column',
                gap: '4px',
                fontSize: '0.88rem'
              }}>
                <div><strong>Promo Code:</strong> <span className="code-tag">{confirmCloseCamp.promo_code}</span></div>
                <div><strong>Campaign ID:</strong> #{confirmCloseCamp.id}</div>
              </div>
              <p style={{ color: 'var(--color-warning)', fontSize: '0.82rem', marginTop: 'var(--space-sm)' }}>
                من بعد الإغلاق، الزبناء الجدد ما غاديش يقدرو يرسلو طلبات جديدة. الطلبات المعلقة الحالية ستبقى محفوظة للمراجعة.
              </p>
            </div>
            <div className="modal-footer">
              <button
                className="btn-retry"
                style={{ background: 'var(--color-danger)' }}
                onClick={handleCloseExecute}
                disabled={submittingAction}
              >
                {submittingAction ? 'جاري الإغلاق...' : '⏹️ تأكيد الإغلاق'}
              </button>
              <button
                className="btn-refresh"
                onClick={() => setConfirmCloseCamp(null)}
                disabled={submittingAction}
              >
                إلغاء
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
