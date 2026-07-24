"use client";

import { BriefcaseMedical, ClipboardCheck, FileStack, LogOut, MonitorCog, SunMoon, UserRound, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { nextTheme, resolvedTheme } from "@/lib/theme";
import { useAuth } from "@/lib/auth/provider";

const links = [
  { href: "/diagnosis", label: "诊断", icon: BriefcaseMedical },
  { href: "/reviews", label: "审核", icon: ClipboardCheck },
  { href: "/cases", label: "案例", icon: FileStack },
  { href: "/system", label: "系统", icon: MonitorCog },
];

export function NavigationRail() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => {
      if (document.documentElement.dataset.themePreference === "system") {
        document.documentElement.dataset.theme = media.matches ? "dark" : "light";
      }
    };
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  function toggleTheme() {
    const current = document.documentElement.dataset.themePreference ?? "system";
    const next = nextTheme(current);
    document.documentElement.dataset.theme = resolvedTheme(next, matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.themePreference = next;
    localStorage.setItem("energy-theme", next);
  }
  return (
    <nav className="navigation-rail" aria-label="主导航">
      <Link className="brand-mark" href="/diagnosis" aria-label="能源诊断首页">能诊</Link>
      {links.map(({ href, label, icon: Icon }) => (
        <Link key={href} href={href} className="rail-link" title={label}
          aria-label={label} aria-current={pathname.startsWith(href) ? "page" : undefined}>
          <Icon size={18} strokeWidth={1.7} aria-hidden />
        </Link>
      ))}
      {user?.role === "admin" ? <Link href="/users" className="rail-link" title="用户管理" aria-label="用户管理" aria-current={pathname.startsWith("/users") ? "page" : undefined}><Users size={18} /></Link> : null}
      <span className="rail-spacer" />
      <button className="icon-button theme-rail" onClick={toggleTheme} aria-label="循环切换 system、light、dark 主题" title="切换主题偏好">
        <SunMoon size={17} />
      </button>
      <Link href="/account" className="rail-link" title={user ? `${user.display_name} · ${user.role}` : "账户"} aria-label="账户"><UserRound size={17} /></Link>
      <button className="icon-button theme-rail" onClick={() => void logout()} aria-label="退出"><LogOut size={17} /></button>
    </nav>
  );
}
