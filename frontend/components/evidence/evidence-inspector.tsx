"use client";

import * as Tabs from "@radix-ui/react-tabs";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DiagnosisResponse, EvidenceDetail, TimeseriesResponse } from "@/lib/api/types";
import { api, errorMessage } from "@/lib/api/browser-client";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { ToolRun } from "@/components/diagnosis/diagnosis-thread";

export function EvidenceCard({ evidence, selected, onSelect }: { evidence: NonNullable<DiagnosisResponse["evidence"]>[number]; selected: boolean; onSelect: () => void }) {
  return <button className="evidence-row" style={{ width: "100%", textAlign: "left", borderTop: 0, borderInline: 0, background: selected ? "var(--surface-subtle)" : "transparent" }} onClick={onSelect}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: ".5rem" }}><strong>{evidence.source_type} · {evidence.source_id}</strong><span className="score">{evidence.final_score == null ? "—" : evidence.final_score.toFixed(3)}</span></div>
    <p>{evidence.summary}</p><div className="score">retrieval {evidence.retrieval_score?.toFixed(2) ?? "—"} · source {evidence.source_reliability?.toFixed(2) ?? evidence.reliability.toFixed(2)} · verify {evidence.verification_score?.toFixed(2) ?? "—"} · freshness {evidence.freshness_score?.toFixed(2) ?? "—"} · alarm {evidence.relevance_to_alarm?.toFixed(2) ?? evidence.relevance.toFixed(2)}</div><div style={{ display: "flex", gap: ".4rem", marginTop: ".5rem" }}><span className={`badge ${evidence.verified ? "complete" : "warning"}`}>{evidence.verified ? "已验证" : "待验证"}</span>{evidence.need_manual_confirmation ? <span className="badge warning">需人工确认</span> : null}</div><div className="row-subtitle mono" title={evidence.citation}>{evidence.citation}</div>
  </button>;
}

export function TimeseriesPanel({ sessionId, response, alarmTime }: { sessionId: string; response: DiagnosisResponse; alarmTime?: string | null }) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [selectedMetrics, setSelectedMetrics] = useState<string[] | null>(null);
  const alarmWindow = (() => {
    if (!alarmTime) return { start: "", end: "" };
    const alarm = new Date(alarmTime);
    const localValue = (value: Date) => {
      const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
      return local.toISOString().slice(0, 16);
    };
    return { start: localValue(new Date(alarm.getTime() - 30 * 60_000)), end: localValue(alarm) };
  })();
  const resolvedStart = start || alarmWindow.start;
  const resolvedEnd = end || alarmWindow.end;
  const params = new URLSearchParams({ run_id: response.run_id });
  if (resolvedStart) params.set("start_time", new Date(resolvedStart).toISOString());
  if (resolvedEnd) params.set("end_time", new Date(resolvedEnd).toISOString());
  const query = useQuery({ queryKey: ["timeseries", sessionId, response.run_id, resolvedStart, resolvedEnd], enabled: !!response.result || !!alarmTime, queryFn: () => api<TimeseriesResponse>(`diagnosis/sessions/${sessionId}/timeseries?${params}`) });
  if (query.isLoading) return <Skeleton rows={4} />;
  if (query.error) return <ErrorState message={errorMessage(query.error)} />;
  if (!query.data) return null;
  const selected = selectedMetrics ?? query.data.series.map((item) => item.metric);
  const rows = new Map<number, Record<string, number>>();
  for (const series of query.data.series) for (const point of series.points) {
    const timestamp = new Date(point.timestamp).getTime();
    rows.set(timestamp, { ...(rows.get(timestamp) ?? {}), timestamp, [series.metric]: point.value });
  }
  const chartData = [...rows.values()].sort((a, b) => a.timestamp - b.timestamp);
  const hasPoints = chartData.length > 0;
  const palette = ["var(--status-info)", "var(--status-complete)", "var(--status-warning)", "var(--text-secondary)"];
  return <div aria-label="诊断时序图">
    <div className="field"><label>时间范围</label><div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem" }}><input className="input" type="datetime-local" value={resolvedStart} onChange={(event) => setStart(event.target.value)} /><input className="input" type="datetime-local" value={resolvedEnd} onChange={(event) => setEnd(event.target.value)} /></div></div>
    <div className="row-subtitle">查询窗口：{new Date(query.data.start_time).toLocaleString("zh-CN")} — {new Date(query.data.end_time).toLocaleString("zh-CN")} · 来源 {query.data.window_source}</div>
    <div style={{ display: "flex", flexWrap: "wrap", gap: ".5rem", marginBlock: ".75rem" }}>{query.data.series.map((series) => <label className="badge" key={series.metric}><input type="checkbox" checked={selected.includes(series.metric)} onChange={() => setSelectedMetrics(selected.includes(series.metric) ? selected.filter((item) => item !== series.metric) : [...selected, series.metric])} />{series.metric}{series.unit ? ` (${series.unit})` : ""} · {series.points.length} 点{series.points.length ? ` · quality ${[...new Set(series.points.map((point) => point.quality ?? "good"))].join("/")}` : ""}</label>)}</div>
    {hasPoints ? <div style={{ height: "20rem", width: "100%" }}><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData}><CartesianGrid stroke="var(--border-subtle)" vertical={false} /><XAxis dataKey="timestamp" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(value) => new Date(value).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })} stroke="var(--text-muted)" /><YAxis stroke="var(--text-muted)" /><Tooltip labelFormatter={(value) => new Date(Number(value)).toLocaleString("zh-CN")} />{alarmTime ? <ReferenceLine x={new Date(alarmTime).getTime()} stroke="var(--status-warning)" strokeDasharray="3 3" label="告警时间" /> : null}{selected.map((metric, index) => <Line key={metric} type="monotone" dataKey={metric} stroke={palette[index % palette.length]} dot={false} connectNulls isAnimationActive={false} />)}</LineChart></ResponsiveContainer></div> : <EmptyState title="暂无时序点" detail={query.data.empty_reason ?? "所选时间范围内没有数据。可调整上方时间范围后重试。"} />}
  </div>;
}

export function EvidenceInspector({ sessionId, response, context, onClose }: { sessionId: string; response: DiagnosisResponse; context?: { alarmId?: string | null; templateId?: string | null; templateVersion?: string | null }; onClose?: () => void }) {
  const sorted = [...(response.evidence ?? [])].sort((a, b) => (b.final_score ?? 0) - (a.final_score ?? 0) || Number(b.verified) - Number(a.verified) || a.source_type.localeCompare(b.source_type));
  const tools = response.tool_summaries ?? [];
  const degraded = response.degraded_components ?? [];
  const [selected, setSelected] = useState(sorted[0]?.evidence_id ?? "");
  const detail = useQuery({ queryKey: ["evidence", sessionId, selected], enabled: !!selected, queryFn: () => api<EvidenceDetail>(`diagnosis/sessions/${sessionId}/evidence/${encodeURIComponent(selected)}`) });
  const runtime = useQuery({ queryKey: ["runtime"], queryFn: async () => (await fetch("/api/runtime")).json() as Promise<{ langfuse_url: string | null }> });
  const alarm = useQuery({ queryKey: ["alarm", context?.alarmId], enabled: !!context?.alarmId, queryFn: () => api<{ trigger_time: string }>(`alarms/${encodeURIComponent(context?.alarmId ?? "")}`) });
  return <Tabs.Root defaultValue="evidence" className="panel inspector">
    <div className="panel-header"><strong>检查器</strong>{onClose ? <button className="button" onClick={onClose} style={{ marginLeft: "auto" }}>关闭</button> : null}</div>
    <Tabs.List className="tabs" aria-label="诊断检查器">
      {[["evidence", "Evidence"], ["timeseries", "Time Series"], ["tools", "Tools"], ["trace", "Trace"]].map(([value, label]) => <Tabs.Trigger className="tab" value={value} key={value}>{label}</Tabs.Trigger>)}
    </Tabs.List>
    <Tabs.Content value="evidence" className="inspector-content">
      {sorted.length ? sorted.map((item) => <EvidenceCard key={item.evidence_id} evidence={item} selected={selected === item.evidence_id} onSelect={() => setSelected(item.evidence_id)} />) : <EmptyState title="暂无 Evidence" />}
      {detail.data ? <div className="result-block"><h3>{detail.data.title}</h3><p>{detail.data.content_excerpt || detail.data.summary}</p><div className="mono">{detail.data.citation}</div><dl>{Object.entries(detail.data.scores).map(([name, value]) => <div key={name}><dt>{name}</dt><dd className="score">{value == null ? "—" : value.toFixed(3)}</dd></div>)}</dl></div> : null}
    </Tabs.Content>
    <Tabs.Content value="timeseries" className="inspector-content"><TimeseriesPanel sessionId={sessionId} response={response} alarmTime={alarm.data?.trigger_time} /></Tabs.Content>
    <Tabs.Content value="tools" className="inspector-content">{tools.length ? tools.map((tool, index) => <ToolRun key={`${String(tool.tool_name)}-${index}`} name={String(tool.tool_name ?? "tool")} status={String(tool.status ?? "unknown")} summary={typeof tool.summary === "string" ? tool.summary : null} hasUsableData={typeof tool.has_usable_data === "boolean" ? tool.has_usable_data : null} resultRef={typeof tool.result_ref === "string" ? tool.result_ref : null} />) : <EmptyState title="暂无工具记录" />}</Tabs.Content>
    <Tabs.Content value="trace" className="inspector-content"><dl><dt>Trace ID</dt><dd className="mono truncate" title={response.trace_id}>{response.trace_id}</dd><dt>Run ID</dt><dd className="mono truncate" title={response.run_id}>{response.run_id}</dd><dt>Template</dt><dd className="mono">{context?.templateId ? `${context.templateId} · ${context.templateVersion ?? "version unknown"}` : "当前响应未公开"}</dd><dt>Prompt version</dt><dd>当前安全响应未公开</dd><dt>降级组件</dt><dd>{degraded.length ? degraded.join("、") : "无"}</dd></dl>{runtime.data?.langfuse_url ? <a className="button" href={runtime.data.langfuse_url} target="_blank" rel="noreferrer">在 LangFuse 中按 Trace ID 查询</a> : <span className="button" aria-disabled="true">LangFuse 未配置</span>}</Tabs.Content>
  </Tabs.Root>;
}
