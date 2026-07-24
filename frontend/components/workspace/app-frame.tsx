"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth/provider";
import { CommandMenu } from "@/components/workspace/command-menu";
import { NavigationRail } from "@/components/workspace/navigation-rail";

export function AppFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const auth = useAuth();
  const authenticationOnly = pathname === "/login"
    || (pathname === "/account/change-password"
      && auth.user?.must_change_password !== false);

  return <div className={`app-frame${authenticationOnly ? " auth-frame" : ""}`}>
    {authenticationOnly ? null : <NavigationRail />}
    <main className="main-surface">{children}</main>
    {authenticationOnly ? null : <CommandMenu />}
  </div>;
}
