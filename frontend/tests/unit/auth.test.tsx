import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChangePasswordForm } from "@/components/auth/change-password-form";
import { LoginForm } from "@/components/auth/login-form";
import { AppFrame } from "@/components/workspace/app-frame";

const replace = vi.fn();
const pathnameState = vi.hoisted(() => ({ value: "/login" }));
const authState = vi.hoisted(() => ({
  value: {
    user: null as { must_change_password: boolean } | null,
    loading: false,
    refresh: vi.fn(),
    logout: vi.fn(),
  },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh: vi.fn() }),
  usePathname: () => pathnameState.value,
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/auth/provider", () => ({
  useAuth: () => authState.value,
}));

afterEach(() => {
  vi.restoreAllMocks();
  replace.mockReset();
  authState.value = {
    ...authState.value,
    user: null,
    loading: false,
  };
  pathnameState.value = "/login";
});

describe("JWT authentication UI and BFF", () => {
  it("renders login and forced-password routes without workspace chrome", () => {
    const login = render(<AppFrame><div>login</div></AppFrame>);
    expect(login.container.firstChild).toHaveClass("auth-frame");
    expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "打开命令菜单" })).not.toBeInTheDocument();
    login.unmount();

    pathnameState.value = "/account/change-password";
    authState.value = {
      ...authState.value,
      user: { must_change_password: true },
    };
    const forced = render(<AppFrame><div>forced</div></AppFrame>);
    expect(forced.container.firstChild).toHaveClass("auth-frame");
    expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "打开命令菜单" })).not.toBeInTheDocument();
  });

  it("login form contains only username/password login and supports password visibility", () => {
    render(<LoginForm />);
    expect(screen.getByRole("heading", { name: "能源诊断" })).toBeInTheDocument();
    expect(screen.getByLabelText("用户名")).toBeInTheDocument();
    const password = screen.getByLabelText("密码");
    expect(password).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByLabelText("显示密码"));
    expect(password).toHaveAttribute("type", "text");
    expect(screen.queryByText(/注册|忘记密码|创建账户/)).not.toBeInTheDocument();
  });

  it("prevents login while an existing refresh session is still being checked", () => {
    authState.value = { ...authState.value, loading: true };
    render(<LoginForm />);
    expect(screen.getByRole("button", { name: "正在检查会话…" })).toBeDisabled();
  });

  it("redirects first-login users to forced password change", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ must_change_password: true }),
    }));
    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "operator01" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "strong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/account/change-password"));
    expect(authState.value.refresh).toHaveBeenCalled();
  });

  it("shows the temporary-unavailable message when login is rate limited", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ error: { code: "RATE_LIMIT_EXCEEDED" } }),
    }));
    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "operator01" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("账号暂时不可用，请稍后重试");
  });

  it("restores a refreshed session from the login page without asking for credentials", async () => {
    authState.value = { ...authState.value, user: { must_change_password: false } };
    render(<LoginForm />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/diagnosis"));
    authState.value = { ...authState.value, user: null };
  });

  it("recovers from a password-change network failure and allows retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<ChangePasswordForm />);
    fireEvent.change(screen.getByLabelText("当前密码"), { target: { value: "old-password" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "new-password-1" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "new-password-1" } });
    fireEvent.click(screen.getByRole("button", { name: "修改密码" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("系统暂时不可用");
    expect(screen.getByRole("button", { name: "修改密码" })).toBeEnabled();
  });

  it("keeps tokens out of browser storage and client components", () => {
    const browserClient = readFileSync(join(process.cwd(), "lib/api/browser-client.ts"), "utf8");
    const authProvider = readFileSync(join(process.cwd(), "lib/auth/provider.tsx"), "utf8");
    expect(`${browserClient}${authProvider}`).not.toMatch(/localStorage.*token|sessionStorage.*token/);
    const cookieHelper = readFileSync(join(process.cwd(), "lib/auth/server.ts"), "utf8");
    expect(cookieHelper).toContain("httpOnly: true");
    expect(cookieHelper).toContain('sameSite: "strict"');
  });
});
