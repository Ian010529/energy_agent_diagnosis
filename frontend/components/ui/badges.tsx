const phaseClass: Record<string, string> = {
  INIT: "muted", PLAN_READY: "running", DATA_FETCHING: "running", EVIDENCE_READY: "running",
  NEED_USER_INPUT: "warning", DRAFT_READY: "warning", REVIEWING: "warning", COMPLETED: "complete", FAILED: "danger",
};

export function StatusBadge({ value }: { value: string }) {
  return <span className={`badge ${phaseClass[value] ?? "muted"}`}>{value}</span>;
}

export function RiskBadge({ value }: { value?: string | null }) {
  const risk = (value ?? "unknown").toLowerCase();
  return <span className={`badge ${risk === "critical" ? "critical" : risk === "high" ? "high" : risk === "medium" ? "warning" : "muted"}`}>风险 {risk}</span>;
}

export function CaseStatusBadge({ value }: { value: string }) { return <StatusBadge value={value} />; }
export function IndexStatusBadge({ value }: { value: string }) { return <StatusBadge value={value} />; }
