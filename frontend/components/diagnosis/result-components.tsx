import { AlertOctagon, ShieldAlert } from "lucide-react";
import type { DiagnosisResponse } from "@/lib/api/types";
import { RiskBadge } from "@/components/ui/badges";

type Result = NonNullable<DiagnosisResponse["result"]>;

export function GuardrailBanner({ decision }: { decision: Result["guardrail_decision"] }) {
  if (!decision) return null;
  const status = decision.status;
  return <div className={`banner ${status === "BLOCKED" ? "danger" : status === "PASSED_WITH_WARNINGS" || status === "NEED_USER_INPUT" ? "warning" : ""}`} role={status === "BLOCKED" ? "alert" : "status"}>
    <strong>Guardrail · {status}</strong>
    {decision.warnings?.length ? <div>{decision.warnings.join(" · ")}</div> : null}
  </div>;
}

export function CandidateCauseCard({ cause }: { cause: NonNullable<Result["candidate_causes"]>[number] }) {
  return <article className="cause">
    <div className="cause-head"><h3>{cause.cause}</h3><span className="score">模型置信度 {Math.round(cause.confidence * 100)}%</span></div>
    <p>仍需结合证据和人工审核。</p>
    {cause.supporting_evidence?.length ? <p><strong>支持证据：</strong>{cause.supporting_evidence.join("、")}</p> : null}
    {cause.contradicting_evidence?.length ? <p><strong>冲突证据：</strong>{cause.contradicting_evidence.join("、")}</p> : null}
    {cause.missing_information?.length ? <p><strong>缺失信息：</strong>{cause.missing_information.join("、")}</p> : null}
    {cause.need_manual_confirmation ? <span className="badge warning">需要人工确认</span> : null}
  </article>;
}

export function RecommendedActionCard({ action }: { action: NonNullable<Result["recommended_actions"]>[number] }) {
  const high = action.risk_level === "high" || action.risk_level === "critical";
  return <article className={`banner ${high ? "danger" : ""}`}>
    <div style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>{high ? <ShieldAlert size={17} /> : null}<strong>{action.description}</strong><RiskBadge value={action.risk_level} /></div>
    <p>执行状态：<strong>{!action.execution_status || action.execution_status === "not_executed" ? "未执行" : action.execution_status}</strong></p>
    {action.requires_human_confirmation ? <p>需要人工确认 · 所需角色：{action.required_role || "未指定"}</p> : null}
    {action.evidence_refs?.length ? <p className="mono">Evidence: {action.evidence_refs.join(", ")}</p> : null}
    {high ? <p><AlertOctagon size={15} /> 本系统仅审核建议，不提供设备执行操作。</p> : null}
  </article>;
}

export function DiagnosisResultBlock({ result }: { result: Result }) {
  return <div className="result-block">
    <GuardrailBanner decision={result.guardrail_decision} />
    <h2 style={{ fontSize: "1rem" }}>诊断摘要</h2><div className="timeline-copy">{result.summary}</div>
    {result.candidate_causes?.length ? <><h2 className="section-title">候选根因</h2>{result.candidate_causes.map((cause, index) => <CandidateCauseCard key={`${cause.cause}-${index}`} cause={cause} />)}</> : null}
    {result.inspection_steps?.length ? <><h2 className="section-title">排查顺序</h2><ol>{result.inspection_steps.map((step) => <li key={step}>{step}</li>)}</ol></> : null}
    {result.safety_notes?.length ? <div className="banner warning"><strong>安全提示</strong><ul>{result.safety_notes.map((note) => <li key={note}>{note}</li>)}</ul></div> : null}
    {result.recommended_actions?.length ? <><h2 className="section-title">建议动作</h2>{result.recommended_actions.map((action) => <RecommendedActionCard key={action.action_id} action={action} />)}</> : null}
  </div>;
}
