import { expect, test } from "@playwright/test";

const quick = [[375, 812], [768, 1024], [1366, 768], [1440, 900], [1920, 1080]] as const;
const full = [[320, 568], [375, 812], [430, 932], [768, 1024], [1024, 768], [1280, 720], [1366, 768], [1440, 900], [1728, 1117], [1920, 1080], [2560, 1440]] as const;
const states = [
  ["INIT", "unknown", null, null],
  ["DATA_FETCHING", "low", null, null],
  ["NEED_USER_INPUT", "medium", null, null],
  ["DRAFT_READY", "high", "pending", null],
  ["REVIEWING", "critical", "reviewing", null],
  ["COMPLETED", "low", "confirmed", null],
  ["FAILED", "unknown", null, "TIMESERIES_UNAVAILABLE"],
] as const;
const sessionList = { items: states.map(([phase, risk, review, failure], index) => ({ session_id: `session-${index}`, run_id: `run-${index}`, source: "alarm", site_id: "SITE-PILOT-01", device_id: `PCS-00${index}`, alarm_id: `alarm-${index}`, alarm_name: index === 4 ? "高风险隔离建议待审核" : "PCS 机柜温度异常", phase, risk_level: risk, trace_id: `trace-${index}`, latest_review_status: review, final_summary: "风道换热能力下降，需要人工审核。", diagnosis_template_id: "pcs_temperature_abnormal_v1", diagnosis_template_version: "1.1.0", alarm_category: "temperature", guardrail_status: index === 4 ? "PASSED_WITH_WARNINGS" : "PASSED", failure_category: failure, created_at: "2026-07-21T08:00:00Z", updated_at: `2026-07-21T08:0${index}:00Z` })), next_cursor: null, has_more: false };

test.beforeEach(async ({ page }) => {
  await page.route(/\/api\/backend\/diagnosis\/sessions(?:\?.*)?$/, (route) => route.fulfill({ json: sessionList }));
  await page.route(/\/api\/backend\/cases(?:\?.*)?$/, (route) => route.fulfill({ json: { items: [{ case_id: "case-approved-01", source_session_id: "session-5", source_run_id: "run-5", source_review_id: "review-5", device_type: "PCS", device_model: "SC5000", alarm_name: "PCS 机柜温度异常", root_cause: "散热风道堵塞", resolution_steps: ["断电后清理风道"], evidence_refs: ["manual-1"], review_status: "APPROVED", case_version: 1, index_status: "INDEXED", graph_projection_status: "PROJECTED", is_active: true, created_by: "operator", created_at: "2026-07-21T08:00:00Z", updated_at: "2026-07-21T08:10:00Z" }], total: 1, next_cursor: null, has_more: false } }));
});

for (const [width, height] of (process.env.VISUAL_FULL_MATRIX === "1" ? full : quick)) {
  for (const theme of ["light", "dark"] as const) test(`diagnosis inbox ${theme} ${width}x${height}`, async ({ page }) => {
      await page.addInitScript((value) => localStorage.setItem("energy-theme", value), theme);
      await page.setViewportSize({ width, height });
      await page.goto("/diagnosis");
      await expect(page.getByRole("heading", { name: "诊断任务" })).toBeVisible();
      await expect(page.getByText("PCS 机柜温度异常").first()).toBeVisible();
      await expect(page).toHaveScreenshot(`diagnosis-inbox-${theme}-${width}x${height}.png`, { animations: "disabled", maxDiffPixelRatio: 0.01 });
    });
}

test("approved case knowledge state", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/cases");
  await expect(page.getByText("散热风道堵塞")).toBeVisible();
  await expect(page).toHaveScreenshot("case-approved-light-1440x900.png", { animations: "disabled", maxDiffPixelRatio: 0.01 });
});

test("200 percent zoom keeps the workspace free of root overflow", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/diagnosis");
  await expect(page.getByText("PCS 机柜温度异常").first()).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });
  await expect(page.getByRole("heading", { name: "诊断任务" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
