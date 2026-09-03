import React, { useState, useEffect, useCallback } from 'react';
import StatCard from '../components/StatCard';
import ActiveCampaignCard from '../components/ActiveCampaignCard';
import RecentRequestsTable from '../components/RecentRequestsTable';
import {
  getDashboardStats,
  getActiveCampaign,
  getPendingRequests,
  acceptRequest,
  rejectRequest,
} from '../services/api';
import './Overview.css';

export default function Overview() {
  const [stats, setStats] = useState(null);
  const [activeCamp, setActiveCamp] = useState(null);
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [statsData, campData, reqsData] = await Promise.all([
        getDashboardStats(),
        getActiveCampaign(),
        getPendingRequests({ limit: 5 }),
      ]);
      setStats(statsData);
      setActiveCamp(campData);
      setRequests(reqsData || []);
    } catch (err) {
      console.error('Failed to load overview data:', err);
      setError(err.message || 'تعذر تحميل البيانات.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAccept = async (id) => {
    try {
      setActionMessage(null);
      await acceptRequest(id);
      setActionMessage({ type: 'success', text: `✅ تم قبول الطلب #${id} بنجاح.` });
      // Refresh stats & requests list
      await loadData();
    } catch (err) {
      setActionMessage({ type: 'error', text: `❌ فشل قبول الطلب: ${err.message}` });
    }
  };

  const handleReject = async (id) => {
    try {
      setActionMessage(null);
      await rejectRequest(id);
      setActionMessage({ type: 'success', text: `✅ تم رفض الطلب #${id} بنجاح.` });
      // Refresh stats & requests list
      await loadData();
    } catch (err) {
      setActionMessage({ type: 'error', text: `❌ فشل رفض الطلب: ${err.message}` });
    }
  };

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

  return (
    <div className="overview-page">
      <div className="page-header">
        <div>
          <h2>لوحة التحكم الرئيسية</h2>
          <p className="page-subtitle">مؤشرات الأداء المباشرة وقائمة المهام المعلقة</p>
        </div>
        <button className="btn-refresh" onClick={loadData} title="تحديث البيانات">
          🔄 تحديث
        </button>
      </div>

      {actionMessage && (
        <div className={`action-alert ${actionMessage.type}`}>
          <span>{actionMessage.text}</span>
          <button className="alert-close" onClick={() => setActionMessage(null)}>×</button>
        </div>
      )}

      {/* 6 Real Database Metric Cards */}
      <section className="stats-grid">
        <StatCard
          title="Promo Codes"
          value={stats?.total_promo_codes ?? 0}
          icon="🎟️"
          variant="primary"
          note={`${stats?.active_promo_codes ?? 0} نشط حالياً`}
        />
        <StatCard
          title="Active Campaign"
          value={stats?.active_campaigns ?? 0}
          icon="🎯"
          variant="info"
          note={activeCamp ? activeCamp.promo_code : 'لا يوجد عرض نشط'}
        />
        <StatCard
          title="Pending Requests"
          value={stats?.pending_requests ?? 0}
          icon="📥"
          variant="warning"
          note="في انتظار المراجعة"
        />
        <StatCard
          title="Customers"
          value={stats?.total_users ?? 0}
          icon="👥"
          variant="default"
          note="إجمالي المستخدمين"
        />
        <StatCard
          title="Accepted"
          value={stats?.accepted_requests ?? 0}
          icon="✅"
          variant="success"
          note="الطلبات المقبولة"
        />
        <StatCard
          title="Rejected"
          value={stats?.rejected_requests ?? 0}
          icon="❌"
          variant="danger"
          note="الطلبات المرفوضة"
        />
      </section>

      {/* Active Campaign Spotlight */}
      <section className="active-campaign-section">
        <ActiveCampaignCard campaign={activeCamp} />
      </section>

      {/* Recent Requests Feed */}
      <section className="recent-requests-section">
        <div className="section-header">
          <h3>أحدث طلبات المشتركين</h3>
          <span className="section-note">
            {requests.length > 0 ? `${requests.length} طلبات معروضة` : 'لا توجد طلبات معلقة'}
          </span>
        </div>
        <RecentRequestsTable
          requests={requests}
          onAccept={handleAccept}
          onReject={handleReject}
        />
      </section>
    </div>
  );
}
