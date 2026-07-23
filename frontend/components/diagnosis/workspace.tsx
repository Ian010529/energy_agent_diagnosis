"use client";

import { useQueries, useQueryClient } from "@tanstack/react-query";
import { PanelRight, RefreshCw } from "lucide-react";
import { useState, useSyncExternalStore } from "react";
import { api, errorMessage } from "@/lib/api/browser-client";
import type { DiagnosisResponse, SessionList, TimelineResponse } from "@/lib/api/types";
import { SessionRow } from "./session-list";
import { DiagnosisThread } from "./diagnosis-thread";
import { EvidenceInspector } from "@/components/evidence/evidence-inspector";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { RiskBadge, StatusBadge } from "@/components/ui/badges";
import { ResponsiveDrawer } from "@/components/workspace/responsive-panels";
import { SessionSidebar, WorkspaceHeader, WorkspaceShell } from "@/components/workspace/workspace-shell";

const WIDE_WORKSPACE = "(min-width: 68.75rem)";
function subscribeWide(onChange: () => void) {
  const query = window.matchMedia(WIDE_WORKSPACE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
function getWideSnapshot() { return window.matchMedia(WIDE_WORKSPACE).matches; }

export function DiagnosisWorkspace({ sessionId }: { sessionId: string }) {
  const client = useQueryClient();
  const wide = useSyncExternalStore(
    subscribeWide,
    getWideSnapshot,
    () => false,
  );
  const [manualInspector, setManualInspector] = useState<boolean | null>(null);
  const inspector = manualInspector ?? wide;
  const setInspector = (open: boolean | ((current: boolean) => boolean)) => setManualInspector(typeof open === "function" ? open(inspector) : open);
  const overlayInspector = !wide;
  const [sessionQuery, timelineQuery, listQuery, metadataQuery, runtimeQuery] = useQueries({ queries: [
    { queryKey: ["session", sessionId], queryFn: () => api<DiagnosisResponse>(`diagnosis/sessions/${sessionId}`), refetchInterval: 15_000 },
    { queryKey: ["timeline", sessionId], queryFn: () => api<TimelineResponse>(`diagnosis/sessions/${sessionId}/timeline`), refetchInterval: 15_000 },
    { queryKey: ["sessions"], queryFn: () => api<SessionList>("diagnosis/sessions?limit=50") },
    { queryKey: ["session-metadata", sessionId], queryFn: () => api<SessionList>(`diagnosis/sessions?limit=1&q=${encodeURIComponent(sessionId)}`) },
    { queryKey: ["runtime"], queryFn: async () => (await fetch("/api/runtime")).json() as Promise<{ role: string }> },
  ] });
  async function recover() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["session", sessionId] }),
      client.invalidateQueries({ queryKey: ["timeline", sessionId] }),
      client.invalidateQueries({ queryKey: ["sessions"] }),
    ]);
  }
  if (sessionQuery.isLoading || timelineQuery.isLoading) return <div className="page"><Skeleton rows={9} /></div>;
  if (sessionQuery.error || timelineQuery.error) return <div className="page"><ErrorState message={errorMessage(sessionQuery.error || timelineQuery.error)} retry={() => void recover()} /></div>;
  if (!sessionQuery.data || !timelineQuery.data) return null;
  const response = sessionQuery.data;
  const sessionItem = listQuery.data?.items.find((item) => item.session_id === sessionId)
    ?? metadataQuery.data?.items.find((item) => item.session_id === sessionId);
  const inspectorContext = { alarmId: sessionItem?.alarm_id, templateId: sessionItem?.diagnosis_template_id, templateVersion: sessionItem?.diagnosis_template_version };
  return <WorkspaceShell inspectorOpen={inspector && !overlayInspector}>
    <SessionSidebar><WorkspaceHeader><strong>诊断任务</strong></WorkspaceHeader><div className="session-list">{listQuery.data?.items.map((item) => <SessionRow item={item} selected={item.session_id === sessionId} key={item.session_id} />)}</div></SessionSidebar>
    <section className="panel thread-panel"><WorkspaceHeader><div className="truncate"><strong>{sessionItem?.alarm_name || "诊断线程"}</strong><div className="row-subtitle mono">{sessionId}</div></div><div className="header-actions"><RiskBadge value={response.result?.risk_level} /><StatusBadge value={response.phase} /><button className="icon-button" onClick={() => void recover()} aria-label="刷新"><RefreshCw size={16} /></button><button className="icon-button" onClick={() => setInspector((open) => !open)} aria-label="切换检查器"><PanelRight size={17} /></button></div></WorkspaceHeader><DiagnosisThread key={sessionId} sessionId={sessionId} response={response} timeline={timelineQuery.data} onRecover={recover} canWrite={runtimeQuery.data?.role != null && runtimeQuery.data.role !== "viewer"} /></section>
    {inspector && !overlayInspector ? <EvidenceInspector key={sessionId} sessionId={sessionId} response={response} context={inspectorContext} onClose={() => setInspector(false)} /> : null}
    {overlayInspector ? <ResponsiveDrawer open={inspector} onOpenChange={setInspector} title="诊断检查器"><EvidenceInspector key={sessionId} sessionId={sessionId} response={response} context={inspectorContext} /></ResponsiveDrawer> : null}
  </WorkspaceShell>;
}
