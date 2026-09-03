/**
 * api.js — Centralized API service communicating with the real FastAPI backend.
 *
 * Base URL: VITE_API_BASE_URL (defaults to http://localhost:8000)
 * Handles:
 * - JWT Authorization header management
 * - Centralized fetch wrapper with 401 redirect to /login
 * - Friendly error messages for 409, 404, 401
 * - Zero secrets stored or exposed
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const TOKEN_KEY = 'rba_token';
const USER_KEY = 'rba_user';

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || null;
  } catch {
    return null;
  }
}

export function setAuthSession(token, username) {
  try {
    if (token) {
      sessionStorage.setItem(TOKEN_KEY, token);
      if (username) sessionStorage.setItem(USER_KEY, username);
    } else {
      sessionStorage.removeItem(TOKEN_KEY);
      sessionStorage.removeItem(USER_KEY);
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  } catch (err) {
    console.error('Session storage error:', err);
  }
}

export function getStoredUser() {
  try {
    return sessionStorage.getItem(USER_KEY) || localStorage.getItem(USER_KEY) || null;
  } catch {
    return null;
  }
}

/**
 * Centralized fetch helper for all backend requests.
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const token = getToken();

  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch (netErr) {
    throw new Error('تعذر الاتصال بالخادم. تأكد من تشغيل الـ Backend.');
  }

  // Handle 401 Unauthorized
  if (response.status === 401) {
    setAuthSession(null, null);
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    throw new Error('انتهت الجلسة. يرجى تسجيل الدخول مجدداً.');
  }

  // Handle 404 Not Found
  if (response.status === 404) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'الطلب أو العنصر غير موجود.');
  }

  // Handle 409 Conflict
  if (response.status === 409) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'هاد الطلب تعالج من قبل.');
  }

  // Handle other errors
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `خطأ في الخادم (${response.status})`);
  }

  // If 204 No Content
  if (response.status === 204) {
    return null;
  }

  return response.json();
}

// ─────────────────────────────────────────────────────────────────────────────
// AUTH
// ─────────────────────────────────────────────────────────────────────────────

export async function login(username, password) {
  const data = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  if (data?.token) {
    setAuthSession(data.token, data.username || username);
  }
  return data;
}

export async function logout() {
  setAuthSession(null, null);
  return { success: true };
}

// ─────────────────────────────────────────────────────────────────────────────
// DASHBOARD
// ─────────────────────────────────────────────────────────────────────────────

export async function getDashboardStats() {
  return request('/api/dashboard/stats');
}

export async function getActiveCampaign() {
  return request('/api/dashboard/active-campaign');
}

// ─────────────────────────────────────────────────────────────────────────────
// PROMO CODES
// ─────────────────────────────────────────────────────────────────────────────

export async function getPromoCodes() {
  return request('/api/promo-codes');
}

export async function getPromoCode(promoId) {
  return request(`/api/promo-codes/${promoId}`);
}

export async function createPromoCode(data) {
  return request('/api/promo-codes', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updatePromoCode(promoId, data) {
  return request(`/api/promo-codes/${promoId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function enablePromoCode(promoId) {
  return request(`/api/promo-codes/${promoId}/enable`, {
    method: 'POST',
  });
}

export async function disablePromoCode(promoId) {
  return request(`/api/promo-codes/${promoId}/disable`, {
    method: 'POST',
  });
}

export async function uploadPromoImage(file) {
  const url = `${API_BASE}/api/promo-codes/upload-image`;
  const token = getToken();
  const formData = new FormData();
  formData.append('file', file);

  const headers = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'فشل رفع الصورة');
  }

  return response.json();
}

// ─────────────────────────────────────────────────────────────────────────────
// CAMPAIGNS
// ─────────────────────────────────────────────────────────────────────────────

export async function getCampaigns({ status, promoCode, limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (status) params.append('status', status);
  if (promoCode) params.append('promo_code', promoCode);
  if (limit) params.append('limit', limit);
  if (offset !== undefined) params.append('offset', offset);

  const query = params.toString() ? `?${params.toString()}` : '';
  return request(`/api/campaigns${query}`);
}

export async function getCampaign(campaignId) {
  return request(`/api/campaigns/${campaignId}`);
}

export async function createCampaign(data) {
  return request('/api/campaigns', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function activateCampaign(campaignId) {
  return request(`/api/campaigns/${campaignId}/activate`, {
    method: 'POST',
  });
}

export async function closeCampaign(campaignId) {
  return request(`/api/campaigns/${campaignId}/close`, {
    method: 'POST',
  });
}

export async function completeCampaign(campaignId) {
  return request(`/api/campaigns/${campaignId}/complete`, {
    method: 'POST',
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// REQUESTS
// ─────────────────────────────────────────────────────────────────────────────

export async function getPendingRequests({ limit = 10, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (limit) params.append('limit', limit);
  if (offset !== undefined) params.append('offset', offset);

  const query = params.toString() ? `?${params.toString()}` : '';
  return request(`/api/requests/pending${query}`);
}

export async function getRequest(requestId) {
  return request(`/api/requests/${requestId}`);
}

export async function acceptRequest(requestId) {
  return request(`/api/requests/${requestId}/accept`, {
    method: 'POST',
  });
}

export async function rejectRequest(requestId) {
  return request(`/api/requests/${requestId}/reject`, {
    method: 'POST',
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// CUSTOMERS
// ─────────────────────────────────────────────────────────────────────────────

export async function getCustomers({ page = 1, limit = 20, search } = {}) {
  const params = new URLSearchParams();
  if (page) params.append('page', page);
  if (limit) params.append('limit', limit);
  if (search && search.trim()) params.append('search', search.trim());

  const query = params.toString() ? `?${params.toString()}` : '';
  return request(`/api/customers${query}`);
}
