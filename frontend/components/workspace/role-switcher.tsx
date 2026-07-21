"use client";

import { useQuery } from "@tanstack/react-query";

export function RoleSwitcher() {
  const runtime = useQuery({ queryKey: ["runtime"], queryFn: async () => {
    const response = await fetch("/api/runtime");
    return response.json() as Promise<{ local: boolean; role: string | null }>;
  }});
  if (!runtime.data?.local) return null;
  return <select className="input" aria-label="本地开发角色" value={runtime.data.role ?? "operator"} style={{ width: "auto", minHeight: "2.25rem" }} onChange={async (event) => {
    await fetch("/api/local-role", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: event.target.value }) });
    location.reload();
  }}><option value="viewer">viewer</option><option value="operator">operator</option><option value="reviewer">reviewer</option><option value="admin">admin</option></select>;
}
