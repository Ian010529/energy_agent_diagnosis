import { expect, test } from "@playwright/test";

test.describe("Phase 7 real backend", () => {
  test.skip(process.env.PHASE7_REAL_E2E !== "1", "requires the Phase 7 Compose stack and pilot dataset");

  test("loads capabilities and creates an alarm diagnosis thread", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/system");
    await expect(page.getByRole("heading", { name: "系统状态" })).toBeVisible();
    await expect(page.getByText("pilot_medium_v1")).toBeVisible({ timeout: 60_000 });
    await page.goto("/diagnosis/new");
    const device = page.getByLabel("设备");
    await expect(device).toBeEnabled();
    await device.selectOption({ index: 1 });
    await page.getByLabel("告警", { exact: true }).selectOption({ index: 1 });
    await page.getByRole("button", { name: "创建诊断线程" }).click();
    await expect(page).toHaveURL(/\/diagnosis\/[a-f0-9-]+/, { timeout: 30_000 });
    await page.getByLabel("诊断消息").fill("请诊断该告警并给出有证据支持的排查顺序");
    await page.getByRole("button", { name: "发送消息" }).click();
    await expect(page.getByText(/实时进度|诊断摘要|需要现场补充/).first()).toBeVisible({ timeout: 60_000 });
  });

  test("runs every registered template through the real SSE protocol", async ({ request }) => {
    test.setTimeout(900_000);
    const capabilities = await (await request.get("/api/backend/capabilities")).json() as {
      templates: Array<{ template_id: string }>;
    };
    expect(capabilities.templates).toHaveLength(5);
    const recentSessions = await (await request.get("/api/backend/diagnosis/sessions?limit=100")).json() as {
      items: Array<{ alarm_id: string | null }>;
    };
    const usedAlarmIds = new Set(recentSessions.items.flatMap((session) => session.alarm_id ? [session.alarm_id] : []));
    let reviewSession = "";
    let sawClarification = false;
    for (const template of capabilities.templates) {
      const alarmResponse = await request.get(`/api/backend/alarms?limit=100&supported=true&template_id=${encodeURIComponent(template.template_id)}`);
      expect(alarmResponse.ok(), `alarm fixture for ${template.template_id}`).toBeTruthy();
      const alarms = ((await alarmResponse.json()) as { items: Array<{ alarm_id: string; alarm_name: string; device_id: string; site_id: string }> }).items;
      const alarm = alarms.find((candidate) => !usedAlarmIds.has(candidate.alarm_id));
      if (!alarm) throw new Error(`No unused pilot alarm for ${template.template_id}`);
      usedAlarmIds.add(alarm.alarm_id);
      const created = await request.post("/api/backend/diagnosis/sessions", {
        headers: { "Idempotency-Key": crypto.randomUUID() },
        data: { source: "alarm", site_id: alarm.site_id, device_id: alarm.device_id, alarm_id: alarm.alarm_id, alarm_name: alarm.alarm_name },
      });
      expect(created.ok()).toBeTruthy();
      const { session_id: sessionId } = await created.json() as { session_id: string };
      const stream = await request.post(`/api/stream/diagnosis/${sessionId}`, { data: { message: "请基于真实证据诊断该告警" } });
      expect(stream.ok(), template.template_id).toBeTruthy();
      let events = await stream.text();
      const answeredQuestionIds = new Set<string>();
      for (let attempt = 0; events.includes("event: need_user_input") && attempt < 3; attempt += 1) {
        sawClarification = true;
        const pending = await (await request.get(`/api/backend/diagnosis/sessions/${sessionId}`)).json() as { memory_revision: number; clarification_questions: Array<{ question_id: string }> };
        const unanswered = pending.clarification_questions.filter((question) => !answeredQuestionIds.has(question.question_id));
        const data = unanswered.length > 0
          ? { message: "现场已按问题逐项核验", expected_memory_revision: pending.memory_revision, clarification_answers: unanswered.map((question) => ({ question_id: question.question_id, answer: "已现场核验并记录，请继续基于现有证据诊断" })) }
          : { message: "补充现场记录：设备型号与铭牌一致，异常测点、端子线束、冗余测点和独立仪表均已逐项核验并留存记录，请基于现有证据继续诊断。", expected_memory_revision: pending.memory_revision };
        const resumed = await request.post(`/api/stream/diagnosis/${sessionId}`, { data });
        expect(resumed.ok()).toBeTruthy();
        unanswered.forEach((question) => answeredQuestionIds.add(question.question_id));
        events = await resumed.text();
      }
      expect(events).toContain("event: completed");
      const completed = await (await request.get(`/api/backend/diagnosis/sessions/${sessionId}`)).json() as {
        evidence_refs: string[];
        result: { recommended_actions: Array<{ execution_status: string }> };
      };
      expect(completed.evidence_refs.length).toBeGreaterThan(0);
      expect(completed.result.recommended_actions.every((action) => action.execution_status === "not_executed")).toBe(true);
      const evidence = await request.get(`/api/backend/diagnosis/sessions/${sessionId}/evidence/${encodeURIComponent(completed.evidence_refs[0])}`);
      expect(evidence.ok(), `evidence detail for ${template.template_id}`).toBeTruthy();
      reviewSession ||= sessionId;
    }
    expect(sawClarification, "at least one template should exercise human clarification").toBe(true);
    const result = await (await request.get(`/api/backend/diagnosis/sessions/${reviewSession}`)).json() as { result: { candidate_causes: Array<{ cause: string }>; inspection_steps: string[] }; evidence_refs: string[] };
    expect(result.evidence_refs.length).toBeGreaterThan(0);
    await request.post("/api/local-role", { data: { role: "reviewer" } });
    const review = await request.post(`/api/backend/diagnosis/sessions/${reviewSession}/review`, { headers: { "Idempotency-Key": crypto.randomUUID() }, data: { review_result: "confirmed", root_cause: result.result.candidate_causes[0].cause, resolution_steps: result.result.inspection_steps.slice(0, 3), evidence_refs: result.evidence_refs } });
    expect(review.ok()).toBeTruthy();
    const { case_id: caseId } = await review.json() as { case_id: string };
    expect(caseId).toBeTruthy();
    await request.post("/api/local-role", { data: { role: "admin" } });
    expect((await request.post(`/api/backend/cases/${caseId}/submit`, { headers: { "Idempotency-Key": crypto.randomUUID() } })).ok()).toBeTruthy();
    const approval = await request.post(`/api/backend/cases/${caseId}/review`, { headers: { "Idempotency-Key": crypto.randomUUID() }, data: { decision: "approve", comment: "Phase 7 E2E approval" } });
    expect(approval.ok()).toBeTruthy();
    const approvedCase = await approval.json() as { review_status: string; index_status: string };
    expect(approvedCase.review_status).toBe("APPROVED");
    expect(["QUEUED", "INDEXED"]).toContain(approvedCase.index_status);
    const persistedCase = await (await request.get(`/api/backend/cases/${caseId}`)).json() as { index_status: string };
    expect(["QUEUED", "INDEXED"]).toContain(persistedCase.index_status);
  });
});
