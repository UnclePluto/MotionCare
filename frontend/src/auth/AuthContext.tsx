import axios from "axios";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";

export type Me = {
  id: number;
  phone: string;
  name: string;
  role: string;
  roles: string[];
  permissions: string[];
};

type AuthContextValue = {
  /** 加载完成前为 undefined；未登录为 null；已登录为用户信息 */
  me: Me | null | undefined;
  loading: boolean;
  error: unknown | null;
  refetchSession: () => Promise<unknown>;
  login: (phone: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function isNotAuthenticatedError(error: unknown): boolean {
  return (
    axios.isAxiosError(error) &&
    (error.response?.status === 401 || error.response?.status === 403)
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        const r = await apiClient.get<Me>("/me/");
        return r.data;
      } catch (e) {
        if (isNotAuthenticatedError(e)) return null;
        throw e;
      }
    },
    retry: false,
    staleTime: 60_000,
  });

  const me = isPending ? undefined : (data ?? null);
  const loading = isPending;
  const sessionError = isError ? error : null;

  const login = useCallback(
    async (phone: string, password: string) => {
      await apiClient.get("/auth/csrf/");
      await apiClient.post("/auth/login/", { phone, password });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    await apiClient.get("/auth/csrf/");
    try {
      await apiClient.post("/auth/logout/");
    } catch {
      // 忽略登出失败（例如会话已过期）
    }
    queryClient.setQueryData(["me"], null);
  }, [queryClient]);

  const value = useMemo(
    () => ({
      me,
      loading,
      error: sessionError,
      refetchSession: refetch,
      login,
      logout,
    }),
    [me, loading, sessionError, refetch, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
