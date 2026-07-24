"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  broadcastLogout,
  refreshSession,
  subscribeAuth,
} from "@/lib/api/browser-client";
import type { UserProfile } from "./types";

interface AuthValue {
  user: UserProfile | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: (all?: boolean) => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export async function currentUser(): Promise<UserProfile | null> {
  let response = await fetch("/api/auth/me", { cache: "no-store" });
  if (response.status === 401) {
    if (!await refreshSession()) return null;
    response = await fetch("/api/auth/me", { cache: "no-store" });
  }
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("auth unavailable");
  return response.json();
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const client = useQueryClient();
  const [loggedOut, setLoggedOut] = useState(false);
  const query = useQuery({ queryKey: ["auth", "me"], queryFn: currentUser, retry: false });
  useEffect(() => {
    return subscribeAuth((message) => {
      if (message === "auth-refreshed") {
        setLoggedOut(false);
        void client.invalidateQueries({
          queryKey: ["auth", "me"],
          refetchType: "none",
        });
      }
      if (message === "auth-logged-out") {
        setLoggedOut(true);
        client.clear();
        client.setQueryData(["auth", "me"], null);
        router.replace("/login");
      }
    });
  }, [client, router]);
  async function logout(all = false) {
    await fetch(all ? "/api/auth/logout-all" : "/api/auth/logout", { method: "POST" });
    setLoggedOut(true);
    broadcastLogout();
    client.clear();
    client.setQueryData(["auth", "me"], null);
    router.replace("/login");
  }
  return <AuthContext.Provider value={{
    user: loggedOut ? null : query.data ?? null,
    loading: loggedOut ? false : query.isLoading || query.isFetching,
    refresh: async () => {
      const result = await query.refetch();
      setLoggedOut(!result.data);
    },
    logout,
  }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
