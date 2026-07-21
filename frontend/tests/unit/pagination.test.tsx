import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionListView } from "@/components/diagnosis/session-list";

const session = (id: string, phase: string) => ({
  session_id: id,
  run_id: `run-${id}`,
  source: "alarm",
  phase,
  risk_level: "low",
  trace_id: `trace-${id}`,
  alarm_name: `告警 ${id}`,
  device_id: "PCS-001",
  created_at: "2026-07-21T08:00:00Z",
  updated_at: "2026-07-21T08:01:00Z",
});

afterEach(() => vi.unstubAllGlobals());

describe("cursor pagination", () => {
  it("requests and appends the next opaque cursor page", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("cursor=next-1")
        ? { items: [session("s2", "COMPLETED")], next_cursor: null, has_more: false }
        : { items: [session("s1", "INIT")], next_cursor: "next-1", has_more: true };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><SessionListView /></QueryClientProvider>);

    expect(await screen.findByText("告警 s1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "加载更多" }));
    expect(await screen.findByText("告警 s2")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("cursor=next-1"),
      expect.objectContaining({ cache: "no-store" }),
    );
  });
});
