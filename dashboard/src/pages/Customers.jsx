import React, { useState, useEffect, useCallback } from 'react';
import { getCustomers } from '../services/api';

const LIMIT = 15;

export default function Customers() {
  const [customers, setCustomers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await getCustomers({
        page,
        limit: LIMIT,
        search: appliedSearch,
      });
      setCustomers(res.customers || []);
      setTotal(res.total || 0);
    } catch (err) {
      console.error('Failed to load customers:', err);
      setError(err.message || 'تعذر تحميل البيانات.');
    } finally {
      setLoading(false);
    }
  }, [page, appliedSearch]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    setAppliedSearch(searchTerm);
  };

  const handleClearSearch = () => {
    setSearchTerm('');
    setAppliedSearch('');
    setPage(1);
  };

  const totalPages = Math.ceil(total / LIMIT) || 1;

  if (loading && customers.length === 0) {
    return (
      <div className="overview-loading">
        <div className="loading-spinner"></div>
        <span>جاري التحميل...</span>
      </div>
    );
  }

  if (error && customers.length === 0) {
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-md)' }}>
        <div>
          <h2>👥 Customers Directory</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginTop: '2px' }}>
            دليل المشتركين المسجلين في البوت ({total} مستخدم)
          </p>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: 'var(--space-sm)' }}>
          <input
            type="text"
            className="form-input"
            style={{ minWidth: '220px', padding: '6px 12px', fontSize: '0.88rem' }}
            placeholder="بحث بالاسم أو Username..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <button type="submit" className="btn-refresh" style={{ background: 'var(--color-primary)', color: '#fff' }}>
            🔍 بحث
          </button>
          {appliedSearch && (
            <button type="button" className="btn-refresh" onClick={handleClearSearch}>
              ✕ إلغاء
            </button>
          )}
        </form>
      </div>

      <div className="requests-table-container">
        <div className="table-responsive">
          <table className="requests-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Telegram ID</th>
                <th>First Name</th>
                <th>Username</th>
                <th>Registered Date</th>
              </tr>
            </thead>
            <tbody>
              {customers.length === 0 ? (
                <tr>
                  <td colSpan="5" style={{ textAlign: 'center', padding: 'var(--space-xl)', color: 'var(--text-muted)' }}>
                    {appliedSearch ? 'لا توجد نتائج مطابقة لبحثك' : 'لا يوجد مشتركون مسجلون حالياً'}
                  </td>
                </tr>
              ) : (
                customers.map((c) => (
                  <tr key={c.id}>
                    <td className="cell-id">#{c.id}</td>
                    <td className="font-mono">{c.telegram_user_id}</td>
                    <td style={{ fontWeight: '500' }}>{c.first_name || '—'}</td>
                    <td style={{ color: 'var(--color-primary)' }}>
                      {c.username ? `@${c.username}` : '—'}
                    </td>
                    <td className="cell-date">
                      {(c.created_at || '').substring(0, 19).replace('T', ' ')}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'var(--space-xs)' }}>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          صفحة {page} من {totalPages} ({total} مشترك)
        </span>
        <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
          <button
            className="btn-refresh"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            style={{ opacity: page <= 1 ? 0.5 : 1 }}
          >
            ⬅️ السابق
          </button>
          <button
            className="btn-refresh"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            style={{ opacity: page >= totalPages ? 0.5 : 1 }}
          >
            ➡️ التالي
          </button>
        </div>
      </div>
    </div>
  );
}
