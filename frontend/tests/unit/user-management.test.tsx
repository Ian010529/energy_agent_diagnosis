import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UserManagement } from "@/components/users/user-management";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/browser-client", () => ({
  api: apiMock,
  errorMessage: () => "保存失败",
}));

const alpha = {
  user_id: "user-1",
  username: "alpha",
  display_name: "Alpha",
  email: null,
  role: "viewer",
  status: "ACTIVE",
  must_change_password: false,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderManagement() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><UserManagement /></QueryClientProvider>);
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("admin user management", () => {
  it("keeps filters and the create action in a responsive toolbar", async () => {
    apiMock.mockResolvedValueOnce({ items: [], next_cursor: null, has_more: false });
    renderManagement();

    const create = await screen.findByRole("button", { name: "添加用户" });
    expect(create.closest(".users-toolbar")).not.toBeNull();
  });

  it("loads subsequent cursor pages", async () => {
    apiMock
      .mockResolvedValueOnce({ items: [alpha], next_cursor: "user-1", has_more: true })
      .mockResolvedValueOnce({
        items: [{ ...alpha, user_id: "user-2", username: "beta", display_name: "Beta" }],
        next_cursor: null,
        has_more: false,
      });
    renderManagement();

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    expect(await screen.findByText("Beta")).toBeInTheDocument();
    expect(apiMock).toHaveBeenLastCalledWith("users?cursor=user-1");
  });

  it("shows an edit failure and returns the save button to an enabled state", async () => {
    apiMock
      .mockResolvedValueOnce({ items: [alpha], next_cursor: null, has_more: false })
      .mockRejectedValueOnce(new Error("duplicate email"));
    renderManagement();

    fireEvent.click(await screen.findByRole("button", { name: /Alpha/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存资料" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("保存失败");
    await waitFor(() => expect(screen.getByRole("button", { name: "保存资料" })).toBeEnabled());
  });

  it("shows status, last login, and creation time in the user editor", async () => {
    apiMock.mockResolvedValueOnce({
      items: [{ ...alpha, last_login_at: "2026-01-02T00:00:00Z" }],
      next_cursor: null,
      has_more: false,
    });
    renderManagement();

    fireEvent.click(await screen.findByRole("button", { name: /Alpha/ }));

    expect(screen.getByText("状态")).toBeInTheDocument();
    expect(screen.getByText("最后登录时间")).toBeInTheDocument();
    expect(screen.getByText("创建时间")).toBeInTheDocument();
  });
});
