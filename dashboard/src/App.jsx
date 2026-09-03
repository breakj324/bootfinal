import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import DashboardLayout from './layouts/DashboardLayout';
import Login from './pages/Login';
import Overview from './pages/Overview';
import PromoCodes from './pages/PromoCodes';
import Campaigns from './pages/Campaigns';
import PendingRequests from './pages/PendingRequests';
import Customers from './pages/Customers';
import Statistics from './pages/Statistics';

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <DashboardLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Overview />} />
          <Route path="promo-codes" element={<PromoCodes />} />
          <Route path="campaigns" element={<Campaigns />} />
          <Route path="pending-requests" element={<PendingRequests />} />
          <Route path="customers" element={<Customers />} />
          <Route path="statistics" element={<Statistics />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
