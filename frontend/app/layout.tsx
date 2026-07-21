import type { Metadata } from "next";
import { QueryProvider } from "@/lib/query/provider";
import { NavigationRail } from "@/components/workspace/navigation-rail";
import { CommandMenu } from "@/components/workspace/command-menu";
import "@/design-system/primitives.css";
import "@/design-system/semantic-light.css";
import "@/design-system/semantic-dark.css";
import "@/design-system/components.css";
import "@/design-system/responsive.css";

export const metadata: Metadata = {
  title: { default: "能源诊断", template: "%s · 能源诊断" },
  description: "能源设备运维诊断工作台",
};

const themeScript = `(function(){try{var t=localStorage.getItem('energy-theme')||'system';var d=t==='system'?(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'):t;document.documentElement.dataset.theme=d;document.documentElement.dataset.themePreference=t}catch(e){}})()`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body>
        <QueryProvider>
          <div className="app-frame">
            <NavigationRail />
            <main className="main-surface">{children}</main>
            <CommandMenu />
          </div>
        </QueryProvider>
      </body>
    </html>
  );
}
