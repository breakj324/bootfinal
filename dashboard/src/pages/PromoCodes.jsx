import React, { useState, useEffect, useCallback } from 'react';
import {
  getPromoCodes,
  getPromoCode,
  createPromoCode,
  updatePromoCode,
  enablePromoCode,
  disablePromoCode,
  uploadPromoImage,
} from '../services/api';

export default function PromoCodes() {
  const [promos, setPromos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [viewingPromo, setViewingPromo] = useState(null);
  const [editingPromo, setEditingPromo] = useState(null);
  const [confirmDisablePromo, setConfirmDisablePromo] = useState(null);

  // Create form state
  const [createForm, setCreateForm] = useState({
    code: '',
    description: '',
    instructions: '',
    requirements: '',
    example_image: '',
  });
  const [createImageFile, setCreateImageFile] = useState(null);
  const [submittingCreate, setSubmittingCreate] = useState(false);
  const [createError, setCreateError] = useState(null);

  // Edit form state
  const [editForm, setEditForm] = useState({
    description: '',
    instructions: '',
    requirements: '',
    example_image: '',
  });
  const [editImageFile, setEditImageFile] = useState(null);
  const [submittingEdit, setSubmittingEdit] = useState(false);
  const [editError, setEditError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getPromoCodes();
      setPromos(data || []);
    } catch (err) {
      console.error('Failed to load promo codes:', err);
      setError(err.message || 'تعذر تحميل البيانات.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Open View Modal ───────────────────────────────────────────────
  const handleOpenView = async (id) => {
    try {
      setActionMessage(null);
      const data = await getPromoCode(id);
      setViewingPromo(data);
    } catch (err) {
      setActionMessage({ type: 'error', text: err.message });
    }
  };

  // ── Open Edit Modal ───────────────────────────────────────────────
  const handleOpenEdit = async (id) => {
    try {
      setActionMessage(null);
      setEditError(null);
      setEditImageFile(null);
      const data = await getPromoCode(id);
      setEditingPromo(data);
      setEditForm({
        description: data.description || '',
        instructions: data.instructions || '',
        requirements: data.requirements || '',
        example_image: data.example_image || '',
      });
    } catch (err) {
      setActionMessage({ type: 'error', text: err.message });
    }
  };

  // ── Handle Create Submit ──────────────────────────────────────────
  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    if (!createForm.code.trim()) {
      setCreateError('كود البرومو مطلوب.');
      return;
    }
    if (!createForm.description.trim()) {
      setCreateError('الوصف مطلوب.');
      return;
    }
    if (!createForm.instructions.trim()) {
      setCreateError('التعليمات مطلوبة.');
      return;
    }
    if (!createForm.requirements.trim()) {
      setCreateError('الشروط والمتطلبات مطلوبة.');
      return;
    }

    try {
      setSubmittingCreate(true);
      setCreateError(null);

      let finalImageUrl = createForm.example_image.trim();
      if (createImageFile) {
        const uploadRes = await uploadPromoImage(createImageFile);
        finalImageUrl = uploadRes.url;
      }

      await createPromoCode({
        code: createForm.code.trim().toUpperCase(),
        description: createForm.description.trim(),
        instructions: createForm.instructions.trim(),
        requirements: createForm.requirements.trim(),
        example_image: finalImageUrl || null,
      });

      setShowCreateModal(false);
      setCreateForm({
        code: '',
        description: '',
        instructions: '',
        requirements: '',
        example_image: '',
      });
      setCreateImageFile(null);
      setActionMessage({ type: 'success', text: '✅ تم إنشاء Promo Code بنجاح.' });
      await loadData();
    } catch (err) {
      setCreateError(err.message || 'فشل إنشاء Promo Code.');
    } finally {
      setSubmittingCreate(false);
    }
  };

  // ── Handle Edit Submit ────────────────────────────────────────────
  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editForm.description.trim()) {
      setEditError('الوصف مطلوب.');
      return;
    }
    if (!editForm.instructions.trim()) {
      setEditError('التعليمات مطلوبة.');
      return;
    }
    if (!editForm.requirements.trim()) {
      setEditError('الشروط والمتطلبات مطلوبة.');
      return;
    }

    try {
      setSubmittingEdit(true);
      setEditError(null);

      let finalImageUrl = editForm.example_image.trim();
      if (editImageFile) {
        const uploadRes = await uploadPromoImage(editImageFile);
        finalImageUrl = uploadRes.url;
      }

      await updatePromoCode(editingPromo.id, {
        description: editForm.description.trim(),
        instructions: editForm.instructions.trim(),
        requirements: editForm.requirements.trim(),
        example_image: finalImageUrl || null,
      });

      setEditingPromo(null);
      setEditImageFile(null);
      setActionMessage({ type: 'success', text: `✅ تم تعديل ${editingPromo.code} بنجاح.` });
      await loadData();
    } catch (err) {
      setEditError(err.message || 'فشل تعديل Promo Code.');
    } finally {
      setSubmittingEdit(false);
    }
  };

  // ── Handle Enable ─────────────────────────────────────────────────
  const handleEnable = async (p) => {
    try {
      setActionMessage(null);
      await enablePromoCode(p.id);
      setActionMessage({ type: 'success', text: `🟢 تم تفعيل ${p.code} بنجاح.` });
      await loadData();
    } catch (err) {
      setActionMessage({ type: 'error', text: err.message });
    }
  };

  // ── Handle Disable Execute ────────────────────────────────────────
  const handleDisableExecute = async () => {
    if (!confirmDisablePromo) return;
    try {
      setActionMessage(null);
      await disablePromoCode(confirmDisablePromo.id);
      setActionMessage({ type: 'success', text: `🔴 تم تعطيل ${confirmDisablePromo.code} بنجاح.` });
      setConfirmDisablePromo(null);
      await loadData();
    } catch (err) {
      setActionMessage({ type: 'error', text: err.message });
      setConfirmDisablePromo(null);
    }
  };

  if (loading && promos.length === 0) {
    return (
      <div className="overview-loading">
        <div className="loading-spinner"></div>
        <span>جاري التحميل...</span>
      </div>
    );
  }

  if (error && promos.length === 0) {
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
          <h2>🎟️ Promo Codes Management</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginTop: '2px' }}>
            إدارة أكواد البرومو، التعليمات، والصور التوضيحية ({promos.length} كود)
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
            ➕ Add Promo Code
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

      {/* Table of Promo Codes */}
      <div className="requests-table-container">
        <div className="table-responsive">
          <table className="requests-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Promo Code</th>
                <th>Description</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {promos.length === 0 ? (
                <tr>
                  <td colSpan="6" style={{ textAlign: 'center', padding: 'var(--space-xl)', color: 'var(--text-muted)' }}>
                    لا توجد Promo Codes مسجلة حالياً
                  </td>
                </tr>
              ) : (
                promos.map((p) => (
                  <tr key={p.id}>
                    <td className="cell-id">#{p.id}</td>
                    <td>
                      <span className="code-tag">{p.code}</span>
                    </td>
                    <td style={{ maxWidth: '280px', color: 'var(--text-secondary)' }} className="truncate">
                      {p.description || '—'}
                    </td>
                    <td>
                      {p.active === 1 ? (
                        <span className="badge badge-success">🟢 ACTIVE</span>
                      ) : (
                        <span className="badge badge-danger">🔴 DISABLED</span>
                      )}
                    </td>
                    <td className="cell-date">{(p.created_at || '').substring(0, 10)}</td>
                    <td>
                      <div className="action-buttons">
                        <button
                          className="btn-refresh"
                          style={{ padding: '3px 8px', fontSize: '0.8rem' }}
                          onClick={() => handleOpenView(p.id)}
                          title="عرض التفاصيل"
                        >
                          👁️ View
                        </button>
                        <button
                          className="btn-refresh"
                          style={{ padding: '3px 8px', fontSize: '0.8rem' }}
                          onClick={() => handleOpenEdit(p.id)}
                          title="تعديل"
                        >
                          ✏️ Edit
                        </button>
                        {p.active === 1 ? (
                          <button
                            className="btn-action btn-reject"
                            style={{ width: 'auto', padding: '0 8px', fontSize: '0.78rem' }}
                            onClick={() => setConfirmDisablePromo(p)}
                            title="تعطيل الكود"
                          >
                            ⏸️ Disable
                          </button>
                        ) : (
                          <button
                            className="btn-action btn-accept"
                            style={{ width: 'auto', padding: '0 8px', fontSize: '0.78rem' }}
                            onClick={() => handleEnable(p)}
                            title="تفعيل الكود"
                          >
                            ▶️ Enable
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── CREATE MODAL ────────────────────────────────────────── */}
      {showCreateModal && (
        <div className="modal-backdrop" onClick={() => setShowCreateModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>➕ إضافة Promo Code جديد</h3>
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
                  <label htmlFor="create-code">Promo Code * (فريد ومحدد)</label>
                  <input
                    id="create-code"
                    type="text"
                    className="form-input font-mono"
                    placeholder="مثال: MRC456"
                    value={createForm.code}
                    onChange={(e) => setCreateForm({ ...createForm, code: e.target.value.toUpperCase() })}
                    disabled={submittingCreate}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="create-desc">الوصف *</label>
                  <input
                    id="create-desc"
                    type="text"
                    className="form-input"
                    placeholder="وصف مختصر للرمز الترويجي"
                    value={createForm.description}
                    onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                    disabled={submittingCreate}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="create-instructions">التعليمات للمشترك *</label>
                  <textarea
                    id="create-instructions"
                    className="form-input"
                    rows="3"
                    placeholder="خطوات التسجيل واستخدام الرمز..."
                    value={createForm.instructions}
                    onChange={(e) => setCreateForm({ ...createForm, instructions: e.target.value })}
                    disabled={submittingCreate}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="create-requirements">الشروط والمتطلبات *</label>
                  <textarea
                    id="create-requirements"
                    className="form-input"
                    rows="2"
                    placeholder="ما يجب أن توضحه لقطة الشاشة..."
                    value={createForm.requirements}
                    onChange={(e) => setCreateForm({ ...createForm, requirements: e.target.value })}
                    disabled={submittingCreate}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="create-image">الصورة التوضيحية (اختياري - رفع ملف أو رابط)</label>
                  <input
                    id="create-image-file"
                    type="file"
                    accept="image/png, image/jpeg, image/webp"
                    className="form-input"
                    style={{ padding: '6px' }}
                    onChange={(e) => setCreateImageFile(e.target.files[0] || null)}
                    disabled={submittingCreate}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="submit"
                  className="btn-retry"
                  disabled={submittingCreate}
                >
                  {submittingCreate ? 'جاري الإنشاء...' : 'Create'}
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

      {/* ── EDIT MODAL ──────────────────────────────────────────── */}
      {editingPromo && (
        <div className="modal-backdrop" onClick={() => setEditingPromo(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>✏️ تعديل Promo Code: <span className="code-tag">{editingPromo.code}</span></h3>
              <button className="modal-close-btn" onClick={() => setEditingPromo(null)}>×</button>
            </div>
            <form onSubmit={handleEditSubmit}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
                {editError && (
                  <div className="action-alert error">
                    <span>{editError}</span>
                  </div>
                )}

                <div className="form-group">
                  <label>Promo Code (غير قابل للتعديل)</label>
                  <input
                    type="text"
                    className="form-input font-mono"
                    value={editingPromo.code}
                    disabled
                    style={{ opacity: 0.6, cursor: 'not-allowed' }}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="edit-desc">الوصف *</label>
                  <input
                    id="edit-desc"
                    type="text"
                    className="form-input"
                    value={editForm.description}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                    disabled={submittingEdit}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="edit-instructions">التعليمات للمشترك *</label>
                  <textarea
                    id="edit-instructions"
                    className="form-input"
                    rows="3"
                    value={editForm.instructions}
                    onChange={(e) => setEditForm({ ...editForm, instructions: e.target.value })}
                    disabled={submittingEdit}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="edit-requirements">الشروط والمتطلبات *</label>
                  <textarea
                    id="edit-requirements"
                    className="form-input"
                    rows="2"
                    value={editForm.requirements}
                    onChange={(e) => setEditForm({ ...editForm, requirements: e.target.value })}
                    disabled={submittingEdit}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="edit-image-file">تحديث الصورة التوضيحية (اختياري)</label>
                  <input
                    id="edit-image-file"
                    type="file"
                    accept="image/png, image/jpeg, image/webp"
                    className="form-input"
                    style={{ padding: '6px' }}
                    onChange={(e) => setEditImageFile(e.target.files[0] || null)}
                    disabled={submittingEdit}
                  />
                  {editForm.example_image && !editImageFile && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      الصورة الحالية: {editForm.example_image}
                    </span>
                  )}
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="submit"
                  className="btn-retry"
                  disabled={submittingEdit}
                >
                  {submittingEdit ? 'جاري الحفظ...' : 'Save Changes'}
                </button>
                <button
                  type="button"
                  className="btn-refresh"
                  onClick={() => setEditingPromo(null)}
                  disabled={submittingEdit}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── VIEW MODAL ──────────────────────────────────────────── */}
      {viewingPromo && (
        <div className="modal-backdrop" onClick={() => setViewingPromo(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>👁️ تفاصيل Promo Code: <span className="code-tag">{viewingPromo.code}</span></h3>
              <button className="modal-close-btn" onClick={() => setViewingPromo(null)}>×</button>
            </div>
            <div className="modal-body">
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-label">الرمز الترويجي</span>
                  <span className="detail-val font-mono">{viewingPromo.code}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">الحالة</span>
                  <span className="detail-val">
                    {viewingPromo.active === 1 ? (
                      <span className="badge badge-success">🟢 ACTIVE</span>
                    ) : (
                      <span className="badge badge-danger">🔴 DISABLED</span>
                    )}
                  </span>
                </div>
                <div className="detail-item" style={{ gridColumn: 'span 2' }}>
                  <span className="detail-label">الوصف</span>
                  <span className="detail-val">{viewingPromo.description || '—'}</span>
                </div>
                <div className="detail-item" style={{ gridColumn: 'span 2' }}>
                  <span className="detail-label">التعليمات</span>
                  <span className="detail-val" style={{ whiteSpace: 'pre-wrap' }}>
                    {viewingPromo.instructions || '—'}
                  </span>
                </div>
                <div className="detail-item" style={{ gridColumn: 'span 2' }}>
                  <span className="detail-label">الشروط والمتطلبات</span>
                  <span className="detail-val" style={{ whiteSpace: 'pre-wrap' }}>
                    {viewingPromo.requirements || '—'}
                  </span>
                </div>
                <div className="detail-item" style={{ gridColumn: 'span 2' }}>
                  <span className="detail-label">الصورة التوضيحية</span>
                  <span className="detail-val" style={{ color: 'var(--color-info)' }}>
                    {viewingPromo.example_image ? viewingPromo.example_image : 'لا توجد صورة'}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">تاريخ الإنشاء</span>
                  <span className="detail-val">{viewingPromo.created_at}</span>
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="btn-refresh"
                onClick={() => setViewingPromo(null)}
              >
                إغلاق
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── DISABLE CONFIRMATION MODAL ──────────────────────────── */}
      {confirmDisablePromo && (
        <div className="modal-backdrop" onClick={() => setConfirmDisablePromo(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '440px' }}>
            <div className="modal-header">
              <h3>⚠️ تأكيد تعطيل Promo Code</h3>
              <button className="modal-close-btn" onClick={() => setConfirmDisablePromo(null)}>×</button>
            </div>
            <div className="modal-body">
              <p style={{ color: 'var(--text-primary)', fontSize: '0.95rem' }}>
                واش متأكد بلي بغيتي تعطل <strong style={{ color: 'var(--color-primary)' }}>{confirmDisablePromo.code}</strong>؟
              </p>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: 'var(--space-xs)' }}>
                إذا تم تعطيله، لن يظهر في قائمة العروض الجديدة للمشتركين.
              </p>
            </div>
            <div className="modal-footer">
              <button
                className="btn-retry"
                style={{ background: 'var(--color-danger)' }}
                onClick={handleDisableExecute}
              >
                نعم، عطل الرمز
              </button>
              <button
                className="btn-refresh"
                onClick={() => setConfirmDisablePromo(null)}
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
