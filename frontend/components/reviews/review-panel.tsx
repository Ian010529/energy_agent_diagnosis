"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/browser-client";
import type { DiagnosisResponse, SessionList } from "@/lib/api/types";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { RoleSwitcher } from "@/components/workspace/role-switcher";

export function ReviewPanel({ sessionId, onDone, canSubmit = true }: { sessionId: string; onDone: () => void; canSubmit?: boolean }) {
  const query = useQuery({ queryKey: ["session", sessionId], queryFn: () => api<DiagnosisResponse>(`diagnosis/sessions/${sessionId}`) });
  const [decision, setDecision] = useState("confirmed");
  const [rootCause, setRootCause] = useState("");
  const [steps, setSteps] = useState("");
  const [comments, setComments] = useState("");
  const [failure, setFailure] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  if (query.isLoading) return <Skeleton />;
  if (!query.data) return <ErrorState message={errorMessage(query.error)} />;
  const response = query.data;
  const blocked = response.result?.guardrail_decision?.status === "BLOCKED";
  async function submit() {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    setFailure("");
    try {
      await api(`diagnosis/sessions/${sessionId}/review`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({
        review_result: decision,
        root_cause: decision === "confirmed" ? rootCause : undefined,
        resolution_steps: decision === "confirmed" ? steps.split("\n").map((item) => item.trim()).filter(Boolean) : [],
        comments: comments || undefined,
        evidence_refs: decision === "confirmed" ? (response.evidence_refs ?? []) : [],
        requested_questions: decision === "needs_more_info" ? comments.split("\n").filter(Boolean).slice(0, 3) : [],
      }) });
      onDone();
    } catch (error) { setFailure(errorMessage(error)); }
    finally { submittingRef.current = false; setSubmitting(false); }
  }
  return <div className="form-stack">
    {!canSubmit ? <div className="banner warning">viewer 为只读角色，不能提交人工审核。</div> : null}
    {blocked ? <div className="banner danger">Guardrail 已阻断，不能确认该诊断。</div> : null}
    <div className="field"><label>审核结论</label><select className="input" disabled={!canSubmit} value={decision} onChange={(event) => setDecision(event.target.value)}><option value="confirmed">confirmed</option><option value="rejected">rejected</option><option value="needs_more_info">needs_more_info</option></select></div>
    {decision === "confirmed" ? <><div className="field"><label>确认根因</label><select className="input" disabled={!canSubmit} value={rootCause} onChange={(event) => setRootCause(event.target.value)}><option value="">选择候选根因</option>{response.result?.candidate_causes?.map((cause) => <option value={cause.cause} key={cause.cause}>{cause.cause}</option>)}</select></div><div className="field"><label>处理步骤（每行一项）</label><textarea className="input" disabled={!canSubmit} value={steps} onChange={(event) => setSteps(event.target.value)} /></div><div className="mono">Evidence refs: {(response.evidence_refs ?? []).join(", ") || "无"}</div></> : null}
    <div className="field"><label>{decision === "needs_more_info" ? "补充问题（最多三行）" : "审核意见"}</label><textarea className="input" disabled={!canSubmit} value={comments} onChange={(event) => setComments(event.target.value)} /></div>
    {failure ? <div className="banner danger" role="alert">{failure}</div> : null}
    {canSubmit ? <button className="button primary" disabled={submitting || blocked || (decision === "confirmed" && (!rootCause || !steps.trim() || !(response.evidence_refs ?? []).length)) || (decision !== "confirmed" && !comments.trim())} onClick={() => void submit()}>{submitting ? "正在提交…" : "提交审核"}</button> : null}
  </div>;
}

export function ReviewsWorkspace() {
  const client = useQueryClient();
  const [selected, setSelected] = useState("");
  const query = useQuery({ queryKey: ["sessions"], queryFn: () => api<SessionList>("diagnosis/sessions?limit=100") });
  const runtime = useQuery({ queryKey: ["runtime"], queryFn: async () => (await fetch("/api/runtime")).json() as Promise<{ role: string }> });
  if (query.isLoading) return <div className="page"><Skeleton rows={8} /></div>;
  if (query.error) return <div className="page"><ErrorState message={errorMessage(query.error)} /></div>;
  const items = (query.data?.items ?? []).filter((item) => ["DRAFT_READY", "REVIEWING", "COMPLETED"].includes(item.phase) && !["confirmed", "rejected"].includes(item.latest_review_status ?? ""));
  return <div className="page"><header className="page-header"><h1>人工审核</h1><span className="meta">{items.length} 条待处理</span><div className="header-actions"><RoleSwitcher /></div></header><div className="content-scroll reviews-layout"><div className="list">{items.map((item) => <button className="list-row" style={{ gridTemplateColumns: "1fr", width: "100%", textAlign: "left", borderInline: 0, borderTop: 0, background: selected === item.session_id ? "var(--surface-subtle)" : "transparent" }} key={item.session_id} onClick={() => setSelected(item.session_id)}><div><div className="row-title">{item.alarm_name || "自由问诊"}</div><div className="row-subtitle">{item.device_id} · {item.phase}</div></div></button>)}</div><div>{selected ? <ReviewPanel sessionId={selected} canSubmit={runtime.data?.role != null && runtime.data.role !== "viewer"} onDone={() => { setSelected(""); void client.invalidateQueries({ queryKey: ["sessions"] }); }} /> : <EmptyState title="选择一条诊断进行审核" />}</div></div></div>;
}
