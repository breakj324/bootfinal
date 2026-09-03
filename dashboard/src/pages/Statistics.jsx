import React, { useState, useEffect, useCallback } from 'react';
import { getDashboardStats } from '../services/api';

export default function Statistics() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getDashboardStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to load stats:', err);
      setError(err.message || 'تعذر تحميل البيانات.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className="overview-loading">
        <div className="loading-spinner"></div>
        <span>جاري التحميل...</span>
      </div>
    );
  }

  if (error) {
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

  const totalReviews = (stats?.accepted_requests || 0) + (stats?.rejected_requests || 0);
  const acceptRate = totalReviews > 0
    ? Math.round(((stats?.accepted_requests || 0) / totalReviews) * 100)
    : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xl)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>📈 Performance & Analytics</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginTop: '2px' }}>
            تحليل معدلات القبول والنشاط العام للنظام
          </p>
        </div>
        <button className="btn-refresh" onClick={loadData} title="تحديث">
          🔄 تحديث
        </button>
      </div>

      <div className="stats-grid">
        <div className="stat-card stat-card-primary">
          <span className="stat-card-title">إجمالي المراجعات</span>
          <span className="stat-card-value">{totalReviews}</span>
          <span className="stat-card-footer">طلبات تمت معالجتها</span>
        </div>
        <div className="stat-card stat-card-success">
          <span className="stat-card-title">نسبة القبول</span>
          <span className="stat-card-value">{acceptRate}%</span>
          <span className="stat-card-footer">{stats?.accepted_requests ?? 0} طلب مقبول</span>
        </div>
        <div className="stat-card stat-card-danger">
          <span className="stat-card-title">نسبة الرفض</span>
          <span className="stat-card-value">{totalReviews > 0 ? 100 - acceptRate : 0}%</span>
          <span className="stat-card-footer">{stats?.rejected_requests ?? 0} طلب مرفوض</span>
        </div>
        <div className="stat-card stat-card-warning">
          <span className="stat-card-title">قيد المراجعة</span>
          <span className="stat-card-value">{stats?.pending_requests ?? 0}</span>
          <span className="stat-card-footer">طلبات في الانتظار</span>
        </div>
      </div>

      <div style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-xl)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-md)',
      }}>
        <h3 style={{ fontSize: '1.1rem', color: 'var(--text-primary)' }}>ملخص كفاءة النظام</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
            <span style={{ color: 'var(--text-secondary)' }}>الطلبات المقبولة</span>
            <span style={{ fontWeight: '600', color: 'var(--color-success)' }}>{stats?.accepted_requests ?? 0}</span>
          </div>
          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{ width: `${acceptRate}%`, background: 'var(--color-success)' }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)', marginTop: 'var(--space-sm)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
            <span style={{ color: 'var(--text-secondary)' }}>الطلبات المرفوضة</span>
            <span style={{ fontWeight: '600', color: 'var(--color-danger)' }}>{stats?.rejected_requests ?? 0}</span>
          </div>
          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{ width: `${totalReviews > 0 ? 100 - acceptRate : 0}%`, background: 'var(--color-danger)' }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
