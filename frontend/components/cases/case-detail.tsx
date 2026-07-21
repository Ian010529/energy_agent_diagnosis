"use client";

import { useQueries, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/browser-client";
import type { CaseHistory, DiagnosisCase } from "@/lib/api/types";
import { CaseStatusBadge, IndexStatusBadge } from "@/components/ui/badges";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { RoleSwitcher } from "@/components/workspace/role-switcher";

export function CaseVersionHistory({ history }: { history: CaseHistory }) {
  return <div className="list">{history.map((event) => <div className="list-row" style={{ gridTemplateColumns: "1fr auto" }} key={event.id}><div><div className="row-title">{event.action}</div><div className="row-subtitle">{event.actor_id} · {event.actor_role}</div></div><div className="row-subtitle">{new Date(event.created_at).toLocaleString("zh-CN")}</div></div>)}</div>;
}

export function CaseDetail({ caseId }: { caseId: string }) {
  const client = useQueryClient();
  const [comment, setComment] = useState("");
  const [failure, setFailure] = useState("");
  const [editing, setEditing] = useState(false);
  const [rootCause, setRootCause] = useState("");
  const [resolutionSteps, setResolutionSteps] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const pendingRef = useRef(false);
  const [caseQuery, historyQuery, runtimeQuery] = useQueries({ queries: [
    { queryKey: ["case", caseId], queryFn: () => api<DiagnosisCase>(`cases/${caseId}`) },
    { queryKey: ["case-history", caseId], queryFn: () => api<CaseHistory>(`cases/${caseId}/history`) },
    { queryKey: ["runtime"], queryFn: async () => (await fetch("/api/runtime")).json() as Promise<{ role: string }> },
  ] });
  if (caseQuery.isLoading || historyQuery.isLoading) return <div className="page"><Skeleton rows={9} /></div>;
  if (!caseQuery.data) return <div className="page"><ErrorState message={errorMessage(caseQuery.error)} /></div>;
  const item = caseQuery.data;
  const role = runtimeQuery.data?.role;
  const canOperate = role != null && role !== "viewer";
  const canReview = role === "reviewer" || role === "admin";
  const canReindex = item.review_status === "APPROVED"
    && ["PENDING", "FAILED", "DEGRADED"].includes(item.index_status ?? "PENDING");
  async function action(path: string, body?: object) {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPendingAction(path);
    setFailure("");
    try { await api(`cases/${caseId}/${path}`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: body ? JSON.stringify(body) : undefined }); await Promise.all([client.invalidateQueries({ queryKey: ["case", caseId] }), client.invalidateQueries({ queryKey: ["case-history", caseId] })]); }
    catch (error) { setFailure(errorMessage(error)); }
    finally { pendingRef.current = false; setPendingAction(""); }
  }
  async function saveDraft() {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPendingAction("save");
    setFailure("");
    try {
      await api(`cases/${caseId}`, { method: "PATCH", body: JSON.stringify({ root_cause: rootCause, resolution_steps: resolutionSteps.split("\n").map((value) => value.trim()).filter(Boolean) }) });
      setEditing(false);
      await client.invalidateQueries({ queryKey: ["case", caseId] });
    } catch (error) { setFailure(errorMessage(error)); }
    finally { pendingRef.current = false; setPendingAction(""); }
  }
  return <div className="page"><header className="page-header"><Link href="/cases" className="icon-button" aria-label="返回"><ArrowLeft size={17} /></Link><h1>案例详情</h1><span className="meta truncate">{caseId}</span><div className="header-actions"><IndexStatusBadge value={item.index_status ?? "PENDING"} /><CaseStatusBadge value={item.review_status ?? "DRAFT"} /><RoleSwitcher /></div></header><div className="content-scroll" style={{ maxWidth: "72rem", width: "100%", margin: "0 auto" }}>
    {failure ? <div className="banner danger" role="alert">{failure}</div> : null}
    <div className="status-grid"><div className="status-cell"><strong>根因</strong>{item.root_cause}</div><div className="status-cell"><strong>设备</strong>{item.device_type || "—"}<br />{item.device_model || "—"}</div><div className="status-cell"><strong>告警</strong>{item.alarm_name || "—"}</div><div className="status-cell"><strong>版本</strong>v{item.case_version}</div><div className="status-cell"><strong>图谱投影</strong>{item.graph_projection_status || "未报告"}</div></div>
    <h2 className="section-title">来源</h2><dl><dt>Session</dt><dd className="mono">{item.source_session_id}</dd><dt>Run</dt><dd className="mono">{item.source_run_id}</dd><dt>Review</dt><dd className="mono">{item.source_review_id}</dd></dl>
    <h2 className="section-title">现象摘要</h2><p>{item.symptom_summary || "—"}</p>
    {editing ? <div className="form-stack"><div className="field"><label>根因</label><textarea className="input" value={rootCause} onChange={(event) => setRootCause(event.target.value)} /></div><div className="field"><label>处理步骤（每行一项）</label><textarea className="input" value={resolutionSteps} onChange={(event) => setResolutionSteps(event.target.value)} /></div><div><button className="button primary" disabled={!!pendingAction || !rootCause.trim() || !resolutionSteps.trim()} onClick={() => void saveDraft()}>{pendingAction === "save" ? "正在保存…" : "保存草稿"}</button> <button className="button" disabled={!!pendingAction} onClick={() => setEditing(false)}>取消</button></div></div> : <><h2 className="section-title">处理步骤</h2><ol>{(item.resolution_steps ?? []).map((step) => <li key={step}>{step}</li>)}</ol></>}
    <h2 className="section-title">Evidence</h2><div className="mono">{(item.evidence_refs ?? []).join(" · ") || "—"}</div>
    <h2 className="section-title">操作</h2><div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
      {item.review_status === "DRAFT" && canOperate ? <><button className="button" disabled={!!pendingAction} onClick={() => { setRootCause(item.root_cause); setResolutionSteps((item.resolution_steps ?? []).join("\n")); setEditing(true); }}>编辑草稿</button><button className="button primary" disabled={!!pendingAction} onClick={() => void action("submit")}>{pendingAction === "submit" ? "正在提交…" : "提交审核"}</button></> : null}
      {item.review_status === "PENDING_REVIEW" && canReview ? <><button className="button primary" disabled={!!pendingAction} onClick={() => void action("review", { decision: "approve", comment })}>{pendingAction === "review" ? "正在处理…" : "审批通过"}</button><button className="button danger" disabled={!!pendingAction} onClick={() => void action("review", { decision: "reject", comment: comment || "审核拒绝" })}>拒绝</button></> : null}
      {item.review_status === "APPROVED" ? <>{canReview && canReindex ? <button className="button" disabled={!!pendingAction} onClick={() => void action("reindex")}>{pendingAction === "reindex" ? "正在索引…" : "重新索引"}</button> : null}{canReview ? <button className="button danger" disabled={!!pendingAction} onClick={() => void action("disable", { reason: comment || "人工停用" })}>{pendingAction === "disable" ? "正在停用…" : "停用"}</button> : null}{canOperate ? <button className="button" disabled={!!pendingAction} onClick={() => void action("revisions", { submit_for_review: false })}>{pendingAction === "revisions" ? "正在创建…" : "创建修订"}</button> : null}</> : null}
    </div>{canOperate ? <div className="field" style={{ marginTop: "1rem", maxWidth: "38rem" }}><label>操作意见</label><input className="input" value={comment} onChange={(event) => setComment(event.target.value)} /></div> : <div className="banner warning" style={{ marginTop: "1rem" }}>viewer 为只读角色，案例操作已隐藏。</div>}
    <h2 className="section-title">审核历史</h2><CaseVersionHistory history={historyQuery.data ?? []} />
  </div></div>;
}
