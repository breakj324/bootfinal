/**
 * useAuth.js — Authentication hook using real JWT state.
 */
import { useState, useCallback } from 'react';
import { login as apiLogin, logout as apiLogout, getToken, getStoredUser } from '../services/api';

export function useAuth() {
  const [token, setToken] = useState(() => getToken());
  const [username, setUsername] = useState(() => getStoredUser());

  const login = useCallback(async (user, pass) => {
    const data = await apiLogin(user, pass);
    setToken(data.token);
    setUsername(data.username || user);
    return data;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setToken(null);
    setUsername(null);
  }, []);

  return {
    isAuthenticated: !!token,
    token,
    username,
    login,
    logout,
  };
}
