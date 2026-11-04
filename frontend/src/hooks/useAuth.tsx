import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiFetch, BootstrapPayload, UserInfo, SchoolInfo } from '../services/api';

interface AuthContextValue {
  loading: boolean;
  authenticated: boolean;
  user: UserInfo | null;
  school: SchoolInfo | null;
  schools: Array<{ id: number; name: string; subdomain: string }>;
  unreadNotifications: number;
  pricing: BootstrapPayload['pricing'] | null;
  refreshBootstrap: () => Promise<BootstrapPayload | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  loading: true,
  authenticated: false,
  user: null,
  school: null,
  schools: [],
  unreadNotifications: 0,
  pricing: null,
  refreshBootstrap: async () => null,
  logout: async () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<BootstrapPayload | null>(null);

  const refreshBootstrap = useCallback(async () => {
    try {
      const res = await apiFetch<BootstrapPayload>('/api/bootstrap');
      setData(res);
      return res;
    } catch {
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshBootstrap();
  }, [refreshBootstrap]);

  const logout = useCallback(async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    await refreshBootstrap();
  }, [refreshBootstrap]);

  return (
    <AuthContext.Provider
      value={{
        loading,
        authenticated: Boolean(data?.authenticated && data?.user),
        user: data?.user || null,
        school: data?.school || null,
        schools: data?.schools || [],
        unreadNotifications: data?.unread_notifications || 0,
        pricing: data?.pricing || null,
        refreshBootstrap,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth() {
  return useContext(AuthContext);
}
