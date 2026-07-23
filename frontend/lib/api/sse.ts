import { ApiError } from "./browser-client";

export const DIAGNOSIS_EVENTS = new Set([
  "intent_identified",
  "data_fetch_started",
  "retrieval_completed",
  "need_user_input",
  "draft_generated",
  "completed",
]);

export type DiagnosisEvent = {
  event: string;
  event_sequence: number;
  session_id: string;
  run_id: string;
  phase: string;
  payload: Record<string, unknown>;
};

export class SSEParser {
  private buffer = "";
  private sequence = 0;

  push(chunk: string): DiagnosisEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const frames = this.buffer.split("\n\n");
    this.buffer = frames.pop() ?? "";
    return frames.flatMap((frame) => {
      let event = "message";
      const data: string[] = [];
      for (const line of frame.split("\n")) {
        if (!line || line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (!data.length || !DIAGNOSIS_EVENTS.has(event)) {
        if (data.length && event !== "message") console.warn(`Unknown diagnosis event: ${event}`);
        return [];
      }
      const payload = JSON.parse(data.join("\n")) as Omit<DiagnosisEvent, "event">;
      if (!Number.isInteger(payload.event_sequence) || payload.event_sequence <= this.sequence) {
        throw new Error("SSE_SEQUENCE_INVALID");
      }
      this.sequence = payload.event_sequence;
      return [{ event, ...payload }];
    });
  }

  get lastSequence() { return this.sequence; }
}

export async function streamDiagnosis(
  sessionId: string,
  body: Record<string, unknown>,
  onEvent: (event: DiagnosisEvent) => void,
  signal?: AbortSignal,
  idempotencyKey?: string,
): Promise<void> {
  const response = await fetch(`/api/stream/diagnosis/${encodeURIComponent(sessionId)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as {
      error?: { code?: string; message?: string };
    };
    throw new ApiError(
      payload.error?.message ?? `Request failed (${response.status})`,
      response.status,
      payload.error?.code ?? "UNKNOWN",
      Number(response.headers.get("retry-after")) || null,
    );
  }
  if (!response.body) throw new Error("STREAM_BODY_MISSING");
  const parser = new SSEParser();
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const event of parser.push(decoder.decode(value, { stream: true }))) onEvent(event);
  }
  for (const event of parser.push(decoder.decode())) onEvent(event);
}
