import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RiskBadge } from "@/components/ui/badges";
import { CandidateCauseCard, GuardrailBanner, RecommendedActionCard } from "@/components/diagnosis/result-components";
import { ClarificationForm, DiagnosisThread } from "@/components/diagnosis/diagnosis-thread";
import { SessionRow } from "@/components/diagnosis/session-list";
import { EvidenceInspector, TimeseriesPanel } from "@/components/evidence/evidence-inspector";
import { ReviewPanel } from "@/components/reviews/review-panel";
import { CaseDetail } from "@/components/cases/case-detail";
import { ResponsiveDrawer } from "@/components/workspace/responsive-panels";

function queryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function json(value: unknown) {
  return Promise.resolve(new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => vi.unstubAllGlobals());

describe("diagnosis safety components", () => {
  it("maps high risk to an explicit risk badge", () => {
    render(<RiskBadge value="high" />);
    expect(screen.getByText("风险 high")).toHaveClass("high");
  });

  it("announces blocked guardrail decisions", () => {
    render(<GuardrailBanner decision={{ status: "BLOCKED", warnings: ["unsafe action"], requires_human_confirmation: true }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("BLOCKED");
  });

  it("never presents a high-risk recommendation as executed", () => {
    render(<RecommendedActionCard action={{ action_id: "a", description: "隔离后检查", risk_level: "high", requires_human_confirmation: true, required_role: "reviewer", evidence_refs: ["e1"], execution_status: "not_executed" }} />);
    expect(screen.getByText(/未执行/)).toBeInTheDocument();
    expect(screen.getByText(/不提供设备执行操作/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /执行/ })).not.toBeInTheDocument();
  });

  it("labels candidate confidence without claiming correctness", () => {
    render(<CandidateCauseCard cause={{ cause: "风道阻塞", confidence: 0.71, supporting_evidence: ["e1"], contradicting_evidence: [], missing_information: [], need_manual_confirmation: true }} />);
    expect(screen.getByText("模型置信度 71%")).toBeInTheDocument();
    expect(screen.getByText(/仍需结合证据和人工审核/)).toBeInTheDocument();
  });
});

describe("workspace components", () => {
  it("renders compact real-session metadata", () => {
    render(<SessionRow item={{ session_id: "s1", run_id: "r1", source: "alarm", phase: "NEED_USER_INPUT", risk_level: "medium", trace_id: "t1", device_id: "PCS-01", alarm_name: "机柜温度异常", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:01:00Z" }} />);
    expect(screen.getByText("机柜温度异常")).toBeInTheDocument();
    expect(screen.getByText("NEED_USER_INPUT")).toBeInTheDocument();
  });

  it("renders backend clarification questions", () => {
    render(<ClarificationForm response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "NEED_USER_INPUT", clarification_questions: [{ question_id: "q1", question: "风扇是否转动？", reason: "确认散热", expected_answer_type: "text" }] }} onSubmit={async () => undefined} disabled={false} />);
    expect(screen.getByLabelText("风扇是否转动？")).toBeRequired();
  });

  it("exposes all inspector tabs without synthetic evidence", () => {
    const client = queryClient();
    render(<QueryClientProvider client={client}><EvidenceInspector sessionId="s1" response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "INIT" }} /></QueryClientProvider>);
    for (const name of ["Evidence", "Time Series", "Tools", "Trace"]) expect(screen.getByRole("tab", { name })).toBeInTheDocument();
  });

  it("loads an alarm time series before a diagnosis result exists", async () => {
    const fetchMock = vi.fn(() => json({
      device_id: "PCS-01",
      start_time: "2026-07-21T07:30:00Z",
      end_time: "2026-07-21T08:00:00Z",
      window_source: "alarm",
      empty_reason: "当前窗口没有匹配的时序点。",
      series: [],
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<QueryClientProvider client={queryClient()}><TimeseriesPanel sessionId="s1" response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "NEED_USER_INPUT" }} alarmTime="2026-07-21T08:00:00Z" /></QueryClientProvider>);
    expect(await screen.findByText("当前窗口没有匹配的时序点。")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue(/2026-07-21T/)).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalled();
  });

  it("reconstructs a diagnosis thread from persisted timeline items", () => {
    render(<DiagnosisThread
      sessionId="s1"
      response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "COMPLETED" }}
      timeline={{ session_id: "s1", history_complete: true, items: [{ timeline_id: "tl1", sequence: 1, kind: "user_message", timestamp: "2026-07-21T08:00:00Z", title: "用户消息", payload: { message: "检查温升" } }] }}
      onRecover={async () => undefined}
    />);
    expect(screen.getByText("检查温升")).toBeInTheDocument();
    expect(screen.getByLabelText("诊断消息")).toBeDisabled();
  });

  it("directs a failed diagnosis to a recoverable new task", () => {
    render(<DiagnosisThread
      sessionId="s1"
      response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "FAILED" }}
      timeline={{ session_id: "s1", history_complete: true, items: [] }}
      onRecover={async () => undefined}
    />);
    expect(screen.getByRole("alert")).toHaveTextContent("本次诊断已失败");
    expect(screen.getByRole("link", { name: "新建诊断" })).toHaveAttribute("href", "/diagnosis/new");
    expect(screen.getByLabelText("诊断消息")).toBeDisabled();
  });

  it("keeps a viewer diagnosis thread read-only", () => {
    render(<DiagnosisThread
      sessionId="s1"
      response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "NEED_USER_INPUT", clarification_questions: [{ question_id: "q1", question: "风扇是否转动？", reason: "确认散热", expected_answer_type: "text" }] }}
      timeline={{ session_id: "s1", history_complete: true, items: [] }}
      onRecover={async () => undefined}
      canWrite={false}
    />);
    expect(screen.getByText(/viewer 为只读角色/)).toBeInTheDocument();
    expect(screen.getByLabelText("诊断消息")).toBeDisabled();
    expect(screen.getByRole("button", { name: "提交补充并继续" })).toBeDisabled();
  });

  it("prevents confirming a guardrail-blocked diagnosis", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({
      session_id: "s1", run_id: "r1", trace_id: "t1", phase: "DRAFT_READY", evidence_refs: ["e1"],
      result: { guardrail_decision: { status: "BLOCKED", warnings: ["unsafe"], requires_human_confirmation: true }, candidate_causes: [{ cause: "风道堵塞" }] },
    })));
    render(<QueryClientProvider client={queryClient()}><ReviewPanel sessionId="s1" onDone={() => undefined} /></QueryClientProvider>);
    expect(await screen.findByText(/Guardrail 已阻断/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提交审核" })).toBeDisabled();
  });

  it("shows only state-machine-valid case actions", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/history")) return json([]);
      if (url === "/api/runtime") return json({ local: false, role: "reviewer" });
      return json({
        case_id: "case-1", source_session_id: "s1", source_run_id: "r1", source_review_id: "review-1",
        root_cause: "风道堵塞", resolution_steps: ["清理风道"], evidence_refs: ["e1"], review_status: "APPROVED",
        index_status: "QUEUED", case_version: 1, is_active: false, created_by: "reviewer", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:01:00Z",
      });
    }));
    render(<QueryClientProvider client={queryClient()}><CaseDetail caseId="case-1" /></QueryClientProvider>);
    expect(await screen.findByText("风道堵塞")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重新索引" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "停用" })).toBeInTheDocument();
  });

  it("keeps viewer workflows read-only", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/history")) return json([]);
      if (url === "/api/runtime") return json({ local: true, role: "viewer" });
      return json({
        case_id: "case-1", source_session_id: "s1", source_run_id: "r1", source_review_id: "review-1",
        root_cause: "风道堵塞", resolution_steps: ["清理风道"], evidence_refs: ["e1"], review_status: "APPROVED",
        index_status: "FAILED", case_version: 1, is_active: true, created_by: "reviewer", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:01:00Z",
      });
    }));
    render(<QueryClientProvider client={queryClient()}><CaseDetail caseId="case-1" /></QueryClientProvider>);
    expect(await screen.findByText(/viewer 为只读角色/)).toBeInTheDocument();
    for (const name of ["重新索引", "停用", "创建修订"]) expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  });

  it("coalesces repeated case action clicks while a write is pending", async () => {
    let finishDisable: ((response: Response) => void) | undefined;
    const pendingDisable = new Promise<Response>((resolve) => { finishDisable = resolve; });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/history")) return json([]);
      if (url === "/api/runtime") return json({ local: true, role: "reviewer" });
      if (url.endsWith("/disable")) return pendingDisable;
      return json({
        case_id: "case-1", source_session_id: "s1", source_run_id: "r1", source_review_id: "review-1",
        root_cause: "风道堵塞", resolution_steps: ["清理风道"], evidence_refs: ["e1"], review_status: "APPROVED",
        index_status: "INDEXED", case_version: 1, is_active: true, created_by: "reviewer", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:01:00Z",
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<QueryClientProvider client={queryClient()}><CaseDetail caseId="case-1" /></QueryClientProvider>);
    const disable = await screen.findByRole("button", { name: "停用" });
    fireEvent.click(disable);
    fireEvent.click(disable);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/disable"))).toHaveLength(1);
    finishDisable?.(await json({}));
    await waitFor(() => expect(screen.getByRole("button", { name: "停用" })).toBeEnabled());
  });

  it("opens the responsive inspector as an accessible dialog", () => {
    const { rerender } = render(<ResponsiveDrawer open={false} onOpenChange={() => undefined} title="证据检查"><p>证据内容</p></ResponsiveDrawer>);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    rerender(<ResponsiveDrawer open onOpenChange={() => undefined} title="证据检查"><p>证据内容</p></ResponsiveDrawer>);
    expect(screen.getByRole("dialog", { name: "证据检查" })).toBeInTheDocument();
  });
});
