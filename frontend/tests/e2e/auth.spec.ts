import { expect, test } from "@playwright/test";

test.describe("Phase 7.5 authentication", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "The shared bootstrap account is exercised once.");

  test.skip(!process.env.PHASE75_REAL_E2E, "requires JWT backend and bootstrap admin");
  test.describe.configure({ mode: "serial" });

  test("admin and operator complete the full authentication and account lifecycle", async ({ browser, page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "能源诊断" })).toBeVisible();
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
    await expect(page.getByText(/注册|忘记密码|创建账户/)).toHaveCount(0);

    await page.getByLabel("用户名").fill("e2e-admin");
    await page.getByLabel("密码", { exact: true }).fill("e2e-admin-password-1");
    await page.getByRole("button", { name: "登录" }).click();
    await expect(page).toHaveURL(/\/account\/change-password/);
    await page.getByLabel("当前密码").fill("e2e-admin-password-1");
    await page.getByLabel("新密码", { exact: true }).fill("e2e-admin-password-2");
    await page.getByLabel("确认新密码").fill("e2e-admin-password-2");
    await page.getByRole("button", { name: "修改密码" }).click();
    await expect(page).toHaveURL(/\/diagnosis/);

    await page.getByLabel("用户管理").click();
    await expect(page).toHaveURL(/\/users/);
    await page.getByRole("button", { name: "添加用户" }).click();
    const form = page.locator("form").filter({ hasText: "添加用户" });
    const inputs = form.locator("input");
    await inputs.nth(0).fill("e2e-operator");
    await inputs.nth(1).fill("E2E Operator");
    await form.locator("select").selectOption("operator");
    await inputs.nth(3).fill("e2e-operator-password-1");
    await inputs.nth(4).fill("e2e-operator-password-1");
    await form.getByRole("button", { name: "创建" }).click();
    await expect(page.getByText("E2E Operator")).toBeVisible();

    await page.getByRole("button", { name: "退出" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("用户名").fill("e2e-operator");
    await page.getByLabel("密码", { exact: true }).fill("e2e-operator-password-1");
    await page.getByRole("button", { name: "登录" }).click();
    await expect(page).toHaveURL(/\/account\/change-password/);
    await page.getByLabel("当前密码").fill("e2e-operator-password-1");
    await page.getByLabel("新密码", { exact: true }).fill("e2e-operator-password-2");
    await page.getByLabel("确认新密码").fill("e2e-operator-password-2");
    await page.getByRole("button", { name: "修改密码" }).click();
    await expect(page).toHaveURL(/\/diagnosis/);
    await expect(page.getByLabel("用户管理")).toHaveCount(0);

    await page.goto("/diagnosis/new");
    await page.getByText("自由问诊", { exact: true }).click();
    await page.getByLabel("描述设备现象或问题").fill("请诊断 PCS 温度持续升高并给出排查顺序");
    await page.getByRole("button", { name: "创建诊断线程" }).click();
    await expect(page).toHaveURL(/\/diagnosis\/[a-f0-9-]+/, { timeout: 30_000 });
    await expect(page.getByText(/实时进度|诊断摘要|需要现场补充/).first()).toBeVisible({
      timeout: 60_000,
    });

    await page.goto("/users");
    await expect(page).toHaveURL(/\/diagnosis/);
    expect(await page.evaluate(async () => (await fetch("/api/backend/users")).status)).toBe(403);

    const refreshCookie = (await page.context().cookies()).find(
      (cookie) => cookie.name === "energy_refresh_token",
    );
    expect(refreshCookie).toBeDefined();
    await page.context().clearCookies();
    await page.context().addCookies([refreshCookie!]);
    await page.goto("/diagnosis");
    await expect(page).toHaveURL(/\/diagnosis/);
    await expect(page.getByRole("heading", { name: "诊断任务" })).toBeVisible();

    const rotatedRefreshCookie = (await page.context().cookies()).find(
      (cookie) => cookie.name === "energy_refresh_token",
    );
    expect(rotatedRefreshCookie).toBeDefined();
    await page.getByRole("button", { name: "退出" }).click();
    await expect(page).toHaveURL(/\/login/);

    await page.context().addCookies([rotatedRefreshCookie!]);
    await page.evaluate(() => window.location.assign("/diagnosis"));
    await expect(page).toHaveURL(/\/login/);

    await page.context().clearCookies();
    await expect(page.getByRole("button", { name: "登录" })).toBeEnabled({ timeout: 10_000 });
    await page.getByLabel("用户名").fill("e2e-operator");
    await page.getByLabel("密码", { exact: true }).fill("e2e-operator-password-2");
    await page.getByRole("button", { name: "登录" }).click();
    await expect(page).toHaveURL(/\/diagnosis/);

    const adminContext = await browser.newContext();
    const adminPage = await adminContext.newPage();
    const adminLogin = await adminContext.request.post(
      "http://127.0.0.1:3000/api/auth/login",
      {
        headers: { Origin: "http://127.0.0.1:3000" },
        data: {
          username: "e2e-admin",
          password: "e2e-admin-password-2",
        },
      },
    );
    expect(adminLogin.ok()).toBe(true);
    await adminPage.goto("/users");
    await expect(adminPage).toHaveURL(/\/users/);
    await expect(adminPage.getByRole("button", { name: /E2E Operator/ })).toBeVisible();
    const users = await (await adminContext.request.get(
      "http://127.0.0.1:3000/api/backend/users",
    )).json();
    const operatorId = users.items.find(
      (item: { username: string }) => item.username === "e2e-operator",
    ).user_id;
    const roleChanged = await adminContext.request.patch(
      `http://127.0.0.1:3000/api/backend/users/${operatorId}`,
      {
        headers: { Origin: "http://127.0.0.1:3000" },
        data: { role: "viewer" },
      },
    );
    expect(roleChanged.ok()).toBe(true);

    await page.reload();
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("button", { name: "登录" })).toBeEnabled({ timeout: 10_000 });
    await page.getByLabel("用户名").fill("e2e-operator");
    await page.getByLabel("密码", { exact: true }).fill("e2e-operator-password-2");
    await page.getByRole("button", { name: "登录" }).click();
    await expect(page).toHaveURL(/\/diagnosis/);
    expect(await page.evaluate(async () => (await fetch("/api/auth/me")).json()))
      .toMatchObject({ role: "viewer" });

    const disabled = await adminContext.request.post(
      `http://127.0.0.1:3000/api/backend/users/${operatorId}/disable`,
      { headers: { Origin: "http://127.0.0.1:3000" } },
    );
    expect(disabled.ok()).toBe(true);

    await page.reload();
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("button", { name: "登录" })).toBeEnabled({ timeout: 10_000 });
    await page.getByLabel("用户名").fill("e2e-operator");
    await page.getByLabel("密码", { exact: true }).fill("e2e-operator-password-2");
    await page.getByRole("button", { name: "登录" }).click();
    await expect(page.locator(".banner[role='alert']")).toHaveText("用户名或密码错误");
    await adminContext.close();
  });

  test("an invalid access cookie can reach the login page without a redirect loop", async ({ page }) => {
    await page.goto("/login");
    await page.context().addCookies([{
      name: "energy_access_token",
      value: "invalid-but-present",
      url: page.url(),
      httpOnly: true,
      sameSite: "Strict",
    }]);

    await page.reload();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: "能源诊断" })).toBeVisible();
  });
});
