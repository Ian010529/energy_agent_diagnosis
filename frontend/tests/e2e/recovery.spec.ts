import { expect, test } from "@playwright/test";

test("recovers session and timeline after an interrupted SSE request", async ({ page }) => {
  const session = { session_id: "recovery-session", run_id: "run-1", trace_id: "trace-1", phase: "INIT", memory_revision: 0, evidence: [], evidence_refs: [], tool_summaries: [], clarification_questions: [], degraded_components: [] };
  const list = { items: [{ session_id: session.session_id, run_id: session.run_id, source: "chat", phase: session.phase, risk_level: "unknown", trace_id: session.trace_id, created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:00:00Z" }], next_cursor: null, has_more: false };
  await page.route("**/api/backend/diagnosis/sessions?**", (route) => route.fulfill({ json: list }));
  await page.route("**/api/backend/diagnosis/sessions/recovery-session/timeline", (route) => route.fulfill({ json: { session_id: session.session_id, history_complete: false, items: [] } }));
  await page.route("**/api/backend/diagnosis/sessions/recovery-session", (route) => route.fulfill({ json: session }));
  await page.route("**/api/stream/diagnosis/recovery-session", (route) => route.fulfill({ status: 503, json: { error: { code: "DEPENDENCY_UNAVAILABLE" } } }));
  await page.goto("/diagnosis/recovery-session");
  await page.getByLabel("诊断消息").fill("继续诊断");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByText("连接已中断，已从服务器恢复最新状态。")).toBeVisible();
});
