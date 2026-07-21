"use client";

import { useQueries } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, errorMessage } from "@/lib/api/browser-client";
import type { Capabilities } from "@/lib/api/types";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { RoleSwitcher } from "@/components/workspace/role-switcher";

type Live = { status: string; trace_id: string };
type Ready = { status: string; dependencies: Record<string, string>; capabilities: Record<string, string>; trace_id: string };
type Runtime = { local: boolean; role: string | null; grafana_url: string | null; langfuse_url: string | null };

export function SystemStatusPanel() {
  const systemStatusStaleTime = 30_000;
  const [capabilities, live, ready, runtime] = useQueries({ queries: [
    { queryKey: ["capabilities"], staleTime: systemStatusStaleTime, queryFn: () => api<Capabilities>("capabilities") },
    { queryKey: ["health-live"], staleTime: systemStatusStaleTime, queryFn: async () => { const response = await fetch("/api/health/live"); return response.json() as Promise<Live>; } },
    { queryKey: ["health-ready"], staleTime: systemStatusStaleTime, retry: false, queryFn: async () => { const response = await fetch("/api/health/ready"); const data = await response.json() as Ready; return data; } },
    { queryKey: ["runtime"], staleTime: systemStatusStaleTime, queryFn: async () => { const response = await fetch("/api/runtime"); return response.json() as Promise<Runtime>; } },
  ] });
  if (capabilities.isLoading) return <Skeleton rows={8} />;
  if (!capabilities.data) return <ErrorState message={errorMessage(capabilities.error)} />;
  const caps = capabilities.data;
  return <>
    <div className={`banner ${ready.data?.status === "ready" ? "" : "warning"}`}><strong>试点技术状态 · CONDITIONAL_GO</strong><div>Live: {live.data?.status ?? "unknown"} · Ready: {ready.data?.status ?? "unknown"}</div></div>
    <div className="status-grid"><div className="status-cell"><strong>数据集</strong>{caps.active_dataset.id}<br /><span className="mono">v{caps.active_dataset.version}</span></div><div className="status-cell"><strong>认证</strong>{caps.auth.mode}<br />Pilot {caps.auth.pilot_mode ? "on" : "off"}</div>{Object.entries(caps.features).map(([name, enabled]) => <div className="status-cell" key={name}><strong>{name}</strong><span className={`badge ${enabled ? "complete" : "muted"}`}>{enabled ? "enabled" : "disabled"}</span></div>)}</div>
    <h2 className="section-title">Provider / dependency</h2><div className="list">{Object.entries(ready.data?.dependencies ?? {}).map(([name, status]) => <div className="list-row" style={{ gridTemplateColumns: "1fr auto" }} key={name}><strong>{name}</strong><span className={`badge ${status === "up" ? "complete" : status === "optional" ? "muted" : "danger"}`}>{status}</span></div>)}</div>
    <h2 className="section-title">诊断模板 · {caps.templates.length}</h2><div className="list">{caps.templates.map((template) => <div className="list-row" style={{ gridTemplateColumns: "1fr auto" }} key={template.template_id}><div><div className="row-title">{template.template_id}</div><div className="row-subtitle">{template.device_type} · {template.alarm_category} · {template.metrics.length} metrics</div></div><span className="mono">v{template.template_version}</span></div>)}</div>
    <h2 className="section-title">外部可观测性</h2><div style={{ display: "flex", gap: ".5rem" }}>{runtime.data?.grafana_url ? <a className="button" href={runtime.data.grafana_url} target="_blank" rel="noreferrer">Grafana <ExternalLink size={14} /></a> : <span className="button" aria-disabled="true">Grafana 未配置</span>}{runtime.data?.langfuse_url ? <a className="button" href={runtime.data.langfuse_url} target="_blank" rel="noreferrer">LangFuse <ExternalLink size={14} /></a> : <span className="button" aria-disabled="true">LangFuse 未配置</span>}</div>
  </>;
}

export function SystemPage() { return <div className="page"><header className="page-header"><h1>系统状态</h1><span className="meta">真实 Provider 与能力</span><div className="header-actions"><RoleSwitcher /></div></header><div className="content-scroll"><SystemStatusPanel /></div></div>; }
