import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RiskBadge } from "@/components/ui/badges";
import { CandidateCauseCard, GuardrailBanner, RecommendedActionCard } from "@/components/diagnosis/result-components";
import { ClarificationForm, DiagnosisComposer, DiagnosisThread } from "@/components/diagnosis/diagnosis-thread";
import { SessionRow } from "@/components/diagnosis/session-list";
import { EvidenceInspector, TimeseriesPanel } from "@/components/evidence/evidence-inspector";
import { ReviewPanel, ReviewsWorkspace } from "@/components/reviews/review-panel";
import { CaseDetail } from "@/components/cases/case-detail";
import { NewDiagnosis } from "@/components/diagnosis/new-diagnosis";
import { ResponsiveDrawer } from "@/components/workspace/responsive-panels";
import { RoleSwitcher } from "@/components/workspace/role-switcher";

const routerPush = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));

function queryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function json(value: unknown) {
  return Promise.resolve(new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  routerPush.mockReset();
  sessionStorage.clear();
});

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
    render(<ClarificationForm response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "NEED_USER_INPUT", clarification_questions: [{ question_id: "q1", question: "风扇是否转动？", reason: "确认散热", expected_answer_type: "text" }] }} onSubmit={async () => true} disabled={false} />);
    expect(screen.getByLabelText("风扇是否转动？")).toBeRequired();
  });

  it("restores an unsent diagnosis draft after the composer remounts", async () => {
    const storageKey = "energy-diagnosis-draft:s1";
    const idempotencyKeys: string[] = [];
    const first = render(<DiagnosisComposer disabled={false} storageKey={storageKey} onSend={async (_message, key) => { idempotencyKeys.push(key); return false; }} />);
    fireEvent.change(screen.getByLabelText("诊断消息"), { target: { value: "继续诊断" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    await waitFor(() => expect(sessionStorage.getItem(storageKey)).toBe("继续诊断"));
    first.unmount();

    render(<DiagnosisComposer disabled={false} storageKey={storageKey} onSend={async (_message, key) => { idempotencyKeys.push(key); return true; }} />);
    expect(await screen.findByDisplayValue("继续诊断")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    await waitFor(() => expect(idempotencyKeys).toHaveLength(2));
    expect(idempotencyKeys[1]).toBe(idempotencyKeys[0]);
  });

  it("exposes all inspector tabs without synthetic evidence", () => {
    const client = queryClient();
    render(<QueryClientProvider client={client}><EvidenceInspector sessionId="s1" response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "INIT" }} /></QueryClientProvider>);
    for (const name of ["Evidence", "Time Series", "Tools", "Trace"]) expect(screen.getByRole("tab", { name })).toBeInTheDocument();
  });

  it("loads the first evidence detail when evidence arrives after the inspector mounts", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/runtime") return json({ langfuse_url: null });
      return json({
        evidence_id: "e1",
        title: "设备证据",
        summary: "风扇转速为零",
        content_excerpt: "现场确认风扇不转",
        citation: "[设备: PCS-01]",
        scores: {},
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = queryClient();
    const view = render(<QueryClientProvider client={client}><EvidenceInspector sessionId="s1" response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "INIT" }} /></QueryClientProvider>);
    expect(screen.getByText("暂无 Evidence")).toBeInTheDocument();
    view.rerender(<QueryClientProvider client={client}><EvidenceInspector sessionId="s1" response={{
      session_id: "s1",
      run_id: "r1",
      trace_id: "t1",
      phase: "EVIDENCE_READY",
      evidence: [{
        evidence_id: "e1",
        source_type: "device",
        source_id: "PCS-01",
        summary: "风扇转速为零",
        citation: "[设备: PCS-01]",
        verified: true,
        reliability: 0.9,
        relevance: 0.9,
      }],
    }} /></QueryClientProvider>);
    expect(await screen.findByText("现场确认风扇不转")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/evidence/e1"))).toBe(true);
  });

  it("shows an evidence detail failure instead of silently hiding the detail", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input) === "/api/runtime") return json({ langfuse_url: null });
      return Promise.resolve(new Response(JSON.stringify({
        error: { code: "BACKEND_UNAVAILABLE", message: "Backend service is unavailable" },
      }), { status: 503, headers: { "Content-Type": "application/json" } }));
    }));
    render(<QueryClientProvider client={queryClient()}><EvidenceInspector sessionId="s1" response={{
      session_id: "s1",
      run_id: "r1",
      trace_id: "t1",
      phase: "EVIDENCE_READY",
      evidence: [{
        evidence_id: "e1",
        source_type: "device",
        source_id: "PCS-01",
        summary: "风扇转速为零",
        citation: "[设备: PCS-01]",
        verified: true,
        reliability: 0.9,
        relevance: 0.9,
      }],
    }} /></QueryClientProvider>);
    expect(await screen.findByText("诊断后端尚未就绪或依赖正在降级。")).toBeInTheDocument();
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

  it("lets an operator ask for the evidence behind a completed diagnosis", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Promise.resolve(new Response("", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DiagnosisThread
      sessionId="s1"
      response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "COMPLETED" }}
      timeline={{ session_id: "s1", history_complete: true, items: [{ timeline_id: "tl1", sequence: 1, kind: "user_message", timestamp: "2026-07-21T08:00:00Z", title: "用户消息", payload: { message: "检查温升" } }] }}
      onRecover={async () => undefined}
    />);
    expect(screen.getByText("检查温升")).toBeInTheDocument();
    expect(screen.getByLabelText("诊断消息")).toBeEnabled();
    fireEvent.change(screen.getByLabelText("诊断消息"), { target: { value: "为什么这样判断" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({
      message: "为什么这样判断",
      followup_mode: "explain_previous_result",
    });
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Idempotency-Key")).toMatch(/.+/);
  });

  it("shows the reviewer questions that an operator must supplement", () => {
    render(<DiagnosisThread
      sessionId="s1"
      response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "NEED_USER_INPUT" }}
      timeline={{ session_id: "s1", history_complete: true, items: [{
        timeline_id: "tl-review",
        sequence: 1,
        kind: "review",
        timestamp: "2026-07-21T08:00:00Z",
        payload: { review_result: "needs_more_info", requested_questions: ["风扇是否转动？", "滤网是否积尘？"] },
      }] }}
      onRecover={async () => undefined}
    />);
    expect(screen.getByText("风扇是否转动？；滤网是否积尘？")).toBeInTheDocument();
  });

  it("reuses clarification idempotency when state recovery fails after the stream", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Promise.resolve(new Response("", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DiagnosisThread
      sessionId="s1"
      response={{
        session_id: "s1",
        run_id: "r1",
        trace_id: "t1",
        phase: "NEED_USER_INPUT",
        memory_revision: 3,
        clarification_questions: [{
          question_id: "q1",
          question: "风扇是否转动？",
          reason: "确认散热",
          expected_answer_type: "text",
        }],
      }}
      timeline={{ session_id: "s1", history_complete: true, items: [] }}
      onRecover={async () => { throw new Error("recovery unavailable"); }}
    />);
    fireEvent.change(screen.getByLabelText("风扇是否转动？"), { target: { value: "不转" } });
    fireEvent.click(screen.getByRole("button", { name: "提交补充并继续" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("button", { name: "提交补充并继续" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "提交补充并继续" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const keys = fetchMock.mock.calls.map(([, init]) => new Headers(init?.headers).get("Idempotency-Key"));
    expect(keys[1]).toBe(keys[0]);
  });

  it("aborts an in-flight diagnosis stream when the user switches sessions", async () => {
    let streamSignal: AbortSignal | undefined;
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      streamSignal = init?.signal ?? undefined;
      streamSignal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
    }));
    vi.stubGlobal("fetch", fetchMock);
    const first = {
      session_id: "s1", run_id: "r1", trace_id: "t1", phase: "INIT" as const,
    };
    const second = {
      session_id: "s2", run_id: "r2", trace_id: "t2", phase: "INIT" as const,
    };
    const view = render(<DiagnosisThread
      key="s1"
      sessionId="s1"
      response={first}
      timeline={{ session_id: "s1", history_complete: true, items: [] }}
      onRecover={async () => undefined}
    />);
    fireEvent.change(screen.getByLabelText("诊断消息"), { target: { value: "检查一号设备" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    await waitFor(() => expect(streamSignal).toBeDefined());

    view.rerender(<DiagnosisThread
      key="s2"
      sessionId="s2"
      response={second}
      timeline={{ session_id: "s2", history_complete: true, items: [] }}
      onRecover={async () => undefined}
    />);
    expect(streamSignal?.aborted).toBe(true);
    expect(screen.getByLabelText("诊断消息")).toHaveValue("");
  });

  it("shows an SSE admission error instead of misreporting a disconnect", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      error: { code: "RATE_LIMITED", message: "Concurrent stream limit exceeded" },
    }), { status: 429, headers: { "Content-Type": "application/json", "Retry-After": "3" } }))));
    render(<DiagnosisThread
      sessionId="s1"
      response={{ session_id: "s1", run_id: "r1", trace_id: "t1", phase: "INIT" }}
      timeline={{ session_id: "s1", history_complete: true, items: [] }}
      onRecover={async () => undefined}
    />);
    fireEvent.change(screen.getByLabelText("诊断消息"), { target: { value: "检查温升" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("3 秒后重试");
    expect(screen.queryByText(/连接已中断/)).not.toBeInTheDocument();
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

  it("keeps diagnosis review read-only for non-reviewer roles", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({
      session_id: "s1", run_id: "r1", trace_id: "t1", phase: "DRAFT_READY", evidence_refs: ["e1"],
      result: { candidate_causes: [{ cause: "风道堵塞" }] },
    })));
    render(<QueryClientProvider client={queryClient()}><ReviewPanel sessionId="s1" onDone={() => undefined} canSubmit={false} /></QueryClientProvider>);
    expect(await screen.findByText(/只有 reviewer 或 admin/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交审核" })).not.toBeInTheDocument();
  });

  it("lets a reviewer record an evidence-backed manual root-cause override", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return json({
        session_id: "s1", run_id: "r1", trace_id: "t1", phase: "COMPLETED", evidence_refs: ["e1"],
        result: { candidate_causes: [{ cause: "风道堵塞" }] },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<QueryClientProvider client={queryClient()}><ReviewPanel sessionId="s1" onDone={() => undefined} /></QueryClientProvider>);
    fireEvent.change(await screen.findByLabelText("确认根因"), { target: { value: "__manual__" } });
    fireEvent.change(screen.getByLabelText("人工确认根因"), { target: { value: "风扇电源接触器失效" } });
    fireEvent.change(screen.getByLabelText("覆盖模型候选的理由"), { target: { value: "现场测量接触器线圈开路" } });
    fireEvent.change(screen.getByLabelText("处理步骤（每行一项）"), { target: { value: "授权断电后更换接触器" } });
    fireEvent.click(screen.getByRole("button", { name: "提交审核" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(body).toMatchObject({
      root_cause: "风扇电源接触器失效",
      override_reason: "现场测量接触器线圈开路",
      evidence_refs: ["e1"],
    });
  });

  it("does not carry review form values into another session", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/runtime") return json({ role: "reviewer" });
      if (url.includes("diagnosis/sessions?")) return json({
        items: [
          { session_id: "s1", run_id: "r1", source: "alarm", phase: "DRAFT_READY", risk_level: "medium", trace_id: "t1", alarm_name: "告警 A", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:00:00Z" },
          { session_id: "s2", run_id: "r2", source: "alarm", phase: "DRAFT_READY", risk_level: "medium", trace_id: "t2", alarm_name: "告警 B", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:00:00Z" },
        ],
        next_cursor: null,
        has_more: false,
      });
      const second = url.endsWith("/s2");
      return json({
        session_id: second ? "s2" : "s1",
        run_id: second ? "r2" : "r1",
        trace_id: second ? "t2" : "t1",
        phase: "DRAFT_READY",
        evidence_refs: [second ? "e2" : "e1"],
        result: { candidate_causes: [{ cause: second ? "二号根因" : "一号根因" }] },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<QueryClientProvider client={queryClient()}><ReviewsWorkspace /></QueryClientProvider>);
    fireEvent.click(await screen.findByRole("button", { name: /告警 A/ }));
    fireEvent.change(await screen.findByLabelText("确认根因"), { target: { value: "一号根因" } });
    fireEvent.change(screen.getByLabelText("处理步骤（每行一项）"), { target: { value: "一号处理步骤" } });

    fireEvent.click(screen.getByRole("button", { name: /告警 B/ }));
    expect(await screen.findByRole("option", { name: "二号根因" })).toBeInTheDocument();
    expect(screen.getByLabelText("确认根因")).toHaveValue("");
    expect(screen.getByLabelText("处理步骤（每行一项）")).toHaveValue("");
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

  it("does not offer case self-review to the case creator", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/history")) return json([]);
      if (url === "/api/runtime") return json({ local: true, role: "reviewer", actor_id: "reviewer-1" });
      return json({
        case_id: "case-1", source_session_id: "s1", source_run_id: "r1", source_review_id: "review-1",
        root_cause: "风道堵塞", resolution_steps: ["清理风道"], evidence_refs: ["e1"], review_status: "PENDING_REVIEW",
        index_status: "PENDING", case_version: 1, is_active: false, created_by: "reviewer-1", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:01:00Z",
      });
    }));
    render(<QueryClientProvider client={queryClient()}><CaseDetail caseId="case-1" /></QueryClientProvider>);
    expect(await screen.findByText(/案例创建人不能审核自己的案例/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "审批通过" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "拒绝" })).not.toBeInTheDocument();
  });

  it("keeps non-reviewer case workflows read-only", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/history")) return json([]);
      if (url === "/api/runtime") return json({ local: true, role: "operator" });
      return json({
        case_id: "case-1", source_session_id: "s1", source_run_id: "r1", source_review_id: "review-1",
        root_cause: "风道堵塞", resolution_steps: ["清理风道"], evidence_refs: ["e1"], review_status: "APPROVED",
        index_status: "FAILED", case_version: 1, is_active: true, created_by: "reviewer", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:01:00Z",
      });
    }));
    render(<QueryClientProvider client={queryClient()}><CaseDetail caseId="case-1" /></QueryClientProvider>);
    expect(await screen.findByText(/只有 reviewer 或 admin/)).toBeInTheDocument();
    for (const name of ["重新索引", "停用", "创建修订"]) expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  });

  it("offers a recoverable index-downline retry after a disable provider failure", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/history")) return json([]);
      if (url === "/api/runtime") return json({ local: true, role: "reviewer", actor_id: "reviewer-2" });
      return json({
        case_id: "case-1", source_session_id: "s1", source_run_id: "r1", source_review_id: "review-1",
        root_cause: "风道堵塞", resolution_steps: ["清理风道"], evidence_refs: ["e1"], review_status: "DISABLED",
        index_status: "FAILED", index_error_code: "CASE_TOMBSTONE_PROVIDER_FAILED", case_version: 1,
        is_active: false, created_by: "reviewer-1", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:01:00Z",
      });
    }));
    render(<QueryClientProvider client={queryClient()}><CaseDetail caseId="case-1" /></QueryClientProvider>);
    expect(await screen.findByRole("button", { name: "重试索引下线" })).toBeInTheDocument();
  });

  it("lets a reviewer revise a rejected case and opens the returned draft", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/history")) return json([]);
      if (url === "/api/runtime") return json({ local: true, role: "reviewer", actor_id: "reviewer-2" });
      if (url.endsWith("/revisions")) return json({
        case_id: "case-2", source_session_id: "s1", source_run_id: "r1", source_review_id: "review-1",
        root_cause: "修订根因", resolution_steps: ["修订步骤"], evidence_refs: ["e1"], review_status: "DRAFT",
        index_status: "PENDING", case_version: 2, is_active: false, created_by: "reviewer-2", created_at: "2026-07-21T08:02:00Z", updated_at: "2026-07-21T08:02:00Z",
      });
      return json({
        case_id: "case-1", source_session_id: "s1", source_run_id: "r1", source_review_id: "review-1",
        root_cause: "被拒根因", resolution_steps: ["原处理步骤"], evidence_refs: ["e1"], review_status: "REJECTED",
        index_status: "PENDING", case_version: 1, is_active: false, created_by: "reviewer-1", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:01:00Z",
      });
    }));
    render(<QueryClientProvider client={queryClient()}><CaseDetail caseId="case-1" /></QueryClientProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "创建修订" }));
    await waitFor(() => expect(routerPush).toHaveBeenCalledWith("/cases/case-2"));
  });

  it("does not present a failed case-history request as an empty audit trail", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/history")) return Promise.resolve(new Response(JSON.stringify({
        error: { code: "BACKEND_UNAVAILABLE", message: "Backend service is unavailable" },
      }), { status: 503, headers: { "Content-Type": "application/json" } }));
      if (url === "/api/runtime") return json({ local: true, role: "reviewer" });
      return json({
        case_id: "case-1", source_session_id: "s1", source_run_id: "r1", source_review_id: "review-1",
        root_cause: "风道堵塞", resolution_steps: ["清理风道"], evidence_refs: ["e1"], review_status: "APPROVED",
        index_status: "INDEXED", case_version: 1, is_active: true, created_by: "reviewer-1", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:01:00Z",
      });
    }));
    render(<QueryClientProvider client={queryClient()}><CaseDetail caseId="case-1" /></QueryClientProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("诊断后端尚未就绪或依赖正在降级。");
    expect(screen.queryByText("审核历史")).not.toBeInTheDocument();
  });

  it("clears stale device and alarm values when a parent diagnosis filter changes", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/runtime") return json({ role: "operator" });
      if (url.includes("/sites")) return json({ items: [
        { site_id: "site-a", display_name: "A", device_count: 1 },
        { site_id: "site-b", display_name: "B", device_count: 1 },
      ], next_cursor: null, has_more: false });
      if (url.includes("/devices")) return json({ items: url.includes("site-b")
        ? [{ device_id: "device-b", device_model: "B" }]
        : [{ device_id: "device-a", device_model: "A" }], next_cursor: null, has_more: false });
      if (url.includes("/alarms")) return json({ items: [{
        alarm_id: url.includes("device-b") ? "alarm-b" : "alarm-a",
        alarm_name: "温度异常",
        alarm_level: "warning",
        supported: true,
      }], next_cursor: null, has_more: false });
      return json({});
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<QueryClientProvider client={queryClient()}><NewDiagnosis /></QueryClientProvider>);

    fireEvent.change(await screen.findByLabelText("场站"), { target: { value: "site-a" } });
    await waitFor(() => expect(screen.getByLabelText("设备")).toHaveTextContent("device-a"));
    fireEvent.change(screen.getByLabelText("设备"), { target: { value: "device-a" } });
    await waitFor(() => expect(screen.getByLabelText("告警")).toHaveTextContent("温度异常"));
    fireEvent.change(screen.getByLabelText("告警"), { target: { value: "alarm-a" } });
    expect(screen.getByLabelText("告警")).toHaveValue("alarm-a");

    fireEvent.change(screen.getByLabelText("场站"), { target: { value: "site-b" } });
    expect(screen.getByLabelText("设备")).toHaveValue("");
    expect(screen.getByLabelText("告警")).toHaveValue("");
  });

  it("shows catalog outages instead of presenting empty diagnosis selectors", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input) === "/api/runtime") return json({ role: "operator" });
      return Promise.resolve(new Response(JSON.stringify({
        error: { code: "BACKEND_UNAVAILABLE", message: "Backend service is unavailable" },
      }), { status: 503, headers: { "Content-Type": "application/json", "Retry-After": "3" } }));
    }));
    render(<QueryClientProvider client={queryClient()}><NewDiagnosis /></QueryClientProvider>);
    expect((await screen.findAllByText("诊断后端尚未就绪或依赖正在降级。")).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("场站")).toBeDisabled();
    expect(screen.getByLabelText("设备")).toBeDisabled();
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

  it("reports a failed local role switch instead of silently reloading", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input) === "/api/runtime") return json({ local: true, role: "operator" });
      return Promise.resolve(new Response(JSON.stringify({ error: "unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }));
    }));
    render(<QueryClientProvider client={queryClient()}><RoleSwitcher /></QueryClientProvider>);
    fireEvent.change(await screen.findByLabelText("本地开发角色"), { target: { value: "reviewer" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("角色切换失败");
    expect(screen.getByLabelText("本地开发角色")).toBeEnabled();
  });
});
