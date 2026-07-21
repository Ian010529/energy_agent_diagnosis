import { describe, expect, it, vi } from "vitest";
import { SSEParser } from "@/lib/api/sse";

const frame = (event: string, sequence: number) =>
  `event: ${event}\ndata: {"event_sequence":${sequence},"session_id":"s","run_id":"r","phase":"DATA_FETCHING","payload":{}}\n\n`;

describe("SSEParser", () => {
  it("handles UTF-8 frames split across chunks and ignores heartbeat comments", () => {
    const parser = new SSEParser();
    expect(parser.push(": heartbeat\n\n" + frame("intent_identified", 1).slice(0, 24))).toEqual([]);
    const events = parser.push(frame("intent_identified", 1).slice(24));
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ event: "intent_identified", event_sequence: 1 });
  });

  it("rejects duplicate or decreasing sequence numbers", () => {
    const parser = new SSEParser();
    parser.push(frame("data_fetch_started", 2));
    expect(() => parser.push(frame("completed", 2))).toThrow("SSE_SEQUENCE_INVALID");
  });

  it("warns and skips unknown events", () => {
    const warning = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expect(new SSEParser().push(frame("private_event", 1))).toEqual([]);
    expect(warning).toHaveBeenCalledWith("Unknown diagnosis event: private_event");
    warning.mockRestore();
  });
});
