"use client";

import { Send, WifiOff } from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { DiagnosisResponse, TimelineResponse } from "@/lib/api/types";
import { streamDiagnosis, type DiagnosisEvent } from "@/lib/api/sse";
import { DiagnosisResultBlock } from "./result-components";

function payloadText(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

const kindTitle: Record<string, string> = {
  user_message: "用户消息", agent_progress: "诊断进度", tool_result: "工具结果",
  clarification_question: "需要补充", clarification_answer: "现场补充",
  diagnosis_result: "诊断结果", review: "人工审核", case_event: "案例事件", error: "执行错误",
};

export function TimelineItem({ item }: { item: TimelineResponse["items"][number] }) {
  const payload = (item.payload ?? {}) as Record<string, unknown>;
  const text = payloadText(payload, "message") || payloadText(payload, "question") || payloadText(payload, "answer") || payloadText(payload, "summary") || item.title || "状态已更新";
  const tone = item.kind === "error" ? "error" : item.kind === "diagnosis_result" ? "complete" : item.kind.includes("progress") ? "running" : "";
  return <article className="timeline-item">
    <span className={`timeline-dot ${tone}`} aria-hidden />
    <div className="timeline-body"><div className="timeline-kicker">{kindTitle[item.kind] ?? item.kind} · {new Date(item.timestamp).toLocaleString("zh-CN")}</div><div className="timeline-copy">{text}</div></div>
  </article>;
}

export function ProgressEvent({ event }: { event: DiagnosisEvent }) {
  return <article className="timeline-item"><span className="timeline-dot running" /><div className="timeline-body"><div className="timeline-kicker">实时进度 · #{event.event_sequence}</div><div className="timeline-copy">{event.event.replaceAll("_", " ")}</div></div></article>;
}

export function ToolRun({ name, status, summary, hasUsableData, resultRef }: { name: string; status: string; summary?: string | null; hasUsableData?: boolean | null; resultRef?: string | null }) {
  return <div className="evidence-row"><div style={{ display: "flex", justifyContent: "space-between" }}><strong>{name}</strong><span className="badge">{status}</span></div>{summary ? <p>{summary}</p> : null}<div className="row-subtitle">可用数据：{hasUsableData == null ? "未报告" : hasUsableData ? "是" : "否"}{resultRef ? ` · ${resultRef}` : ""}</div></div>;
}

export function ClarificationForm({ response, onSubmit, disabled }: { response: DiagnosisResponse; onSubmit: (message: string, answers: Array<{ question_id: string; answer: string }>) => Promise<void>; disabled: boolean }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const questions = response.clarification_questions ?? [];
  if (response.phase !== "NEED_USER_INPUT" || !questions.length) return null;
  return <form className="banner warning" onSubmit={(event) => { event.preventDefault(); void onSubmit("现场补充信息", questions.map((q) => ({ question_id: q.question_id, answer: answers[q.question_id] ?? "" }))); }}>
    <strong>需要现场补充</strong>
    {questions.map((question) => <div className="field" key={question.question_id}><label htmlFor={question.question_id}>{question.question}</label><input required className="input" id={question.question_id} value={answers[question.question_id] ?? ""} onChange={(event) => setAnswers((old) => ({ ...old, [question.question_id]: event.target.value }))} /></div>)}
    <button className="button" disabled={disabled}>提交补充并继续</button>
  </form>;
}

export function DiagnosisComposer({ disabled, onSend }: { disabled: boolean; onSend: (message: string) => Promise<void> }) {
  const [value, setValue] = useState("");
  async function submit(event: FormEvent) { event.preventDefault(); if (!value.trim()) return; const message = value.trim(); await onSend(message); setValue(""); }
  return <form className="composer" onSubmit={submit}><div className="composer-box"><textarea aria-label="诊断消息" placeholder="补充现象、追问依据或继续诊断…" value={value} onChange={(event) => setValue(event.target.value)} disabled={disabled} /><button className="icon-button" aria-label="发送消息" disabled={disabled || !value.trim()}><Send size={17} /></button></div></form>;
}

export function DiagnosisThread({ sessionId, response, timeline, onRecover, canWrite = true }: { sessionId: string; response: DiagnosisResponse; timeline: TimelineResponse; onRecover: () => Promise<void>; canWrite?: boolean }) {
  const [events, setEvents] = useState<DiagnosisEvent[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [disconnected, setDisconnected] = useState(false);
  const liveRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const initialMessageSentRef = useRef(false);
  useEffect(() => () => controllerRef.current?.abort(), []);
  useEffect(() => {
    if (!streaming) return;
    const startedAt = Date.now();
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1_000);
    return () => window.clearInterval(timer);
  }, [streaming]);
  const send = useCallback(async (message: string, answers: Array<{ question_id: string; answer: string }> = []) => {
    setElapsedSeconds(0); setStreaming(true); setDisconnected(false); setEvents([]);
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      await streamDiagnosis(sessionId, { message, clarification_answers: answers, expected_memory_revision: response.memory_revision }, (event) => setEvents((old) => [...old, event]), controller.signal);
      await onRecover();
    } catch {
      if (!controller.signal.aborted) {
        setDisconnected(true);
        await onRecover();
      }
    } finally { if (controllerRef.current === controller) controllerRef.current = null; setStreaming(false); }
  }, [onRecover, response.memory_revision, sessionId]);
  useEffect(() => {
    if (!canWrite) return;
    if (initialMessageSentRef.current) return;
    const key = `energy-initial-message:${sessionId}`;
    const message = sessionStorage.getItem(key);
    if (!message) return;
    initialMessageSentRef.current = true;
    sessionStorage.removeItem(key);
    queueMicrotask(() => void send(message));
  }, [canWrite, send, sessionId]);
  const blocked = response.result?.guardrail_decision?.status === "BLOCKED";
  const failed = response.phase === "FAILED";
  return <>
    <div className="thread" ref={liveRef}>
      {disconnected ? <div className="banner warning" role="status"><WifiOff size={16} />连接已中断，已从服务器恢复最新状态。</div> : null}
      {!canWrite ? <div className="banner warning">viewer 为只读角色，不能发送消息或提交现场补充。</div> : null}
      {failed ? <div className="banner danger" role="alert">本次诊断已失败，已完成的进度仍保留在时间线中。<Link className="button" href="/diagnosis/new">新建诊断</Link></div> : null}
      {blocked ? <div className="banner danger" role="alert">该结果已被 Guardrail 阻断，不能作为诊断成功或提交确认。</div> : null}
      {timeline.items.map((item) => <TimelineItem item={item} key={item.timeline_id} />)}
      {events.map((event) => <ProgressEvent event={event} key={`${event.run_id}-${event.event_sequence}`} />)}
      <ClarificationForm response={response} onSubmit={send} disabled={streaming || !canWrite} />
      {response.result ? <DiagnosisResultBlock result={response.result} /> : null}
      <div aria-live="polite" className="timeline-kicker">{streaming ? `诊断正在运行 · ${elapsedSeconds} 秒（混合检索和模型调用通常需要 10–60 秒）` : disconnected ? "流已恢复" : ""}</div>
    </div>
    <DiagnosisComposer disabled={!canWrite || streaming || failed || response.phase === "COMPLETED"} onSend={(message) => send(message)} />
  </>;
}
