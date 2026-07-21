"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api/browser-client";
import type { CaseListResponse } from "@/lib/api/types";
import { CaseStatusBadge, IndexStatusBadge } from "@/components/ui/badges";
import { EmptyState, RequestErrorState, Skeleton } from "@/components/ui/states";

export function CaseList() {
  const [filters, setFilters] = useState({ review_status: "", device_type: "", device_model: "", alarm_name: "", created_by: "", is_active: "" });
  const [cursors, setCursors] = useState<Array<string | null>>([null]);
  const page = cursors.length - 1;
  const params = new URLSearchParams({ limit: "50", sort: "updated_at_desc" });
  for (const [name, value] of Object.entries(filters)) if (value) params.set(name, value);
  if (cursors[page]) params.set("cursor", cursors[page] ?? "");
  const query = useQuery({ queryKey: ["cases", filters, cursors[page]], queryFn: () => api<CaseListResponse>(`cases?${params}`) });
  if (query.isLoading) return <Skeleton rows={8} />;
  if (query.error) return <RequestErrorState error={query.error} retry={() => void query.refetch()} />;
  function update(name: keyof typeof filters, value: string) {
    setFilters((old) => ({ ...old, [name]: value }));
    setCursors([null]);
  }
  return <><div className="filter-bar">
    <select className="input" aria-label="案例状态" value={filters.review_status} onChange={(event) => update("review_status", event.target.value)}><option value="">全部状态</option>{["DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", "DISABLED", "SUPERSEDED"].map((value) => <option key={value}>{value}</option>)}</select>
    <input className="input" aria-label="设备类型" placeholder="设备类型" value={filters.device_type} onChange={(event) => update("device_type", event.target.value)} />
    <input className="input" aria-label="设备型号" placeholder="设备型号" value={filters.device_model} onChange={(event) => update("device_model", event.target.value)} />
    <input className="input" aria-label="告警名称" placeholder="告警名称" value={filters.alarm_name} onChange={(event) => update("alarm_name", event.target.value)} />
    <input className="input" aria-label="创建人" placeholder="创建人" value={filters.created_by} onChange={(event) => update("created_by", event.target.value)} />
    <select className="input" aria-label="是否有效" value={filters.is_active} onChange={(event) => update("is_active", event.target.value)}><option value="">全部有效性</option><option value="true">有效</option><option value="false">无效</option></select>
  </div>
  {!query.data?.items.length ? <EmptyState title="暂无案例" detail="确认诊断后生成的草稿会出现在这里。" /> : <div className="list">{query.data.items.map((item) => <Link className="list-row" href={`/cases/${item.case_id}`} key={item.case_id}>
    <div><div className="row-title">{item.root_cause}</div><div className="row-subtitle">{item.device_type || "未知设备"} · {item.device_model || "未知型号"} · {item.alarm_name || "无告警"}</div></div>
    <div><div className="row-title">v{item.case_version}</div><div className="row-subtitle">Graph {item.graph_projection_status || "未报告"} · {new Date(item.updated_at).toLocaleString("zh-CN")}</div></div>
    <IndexStatusBadge value={item.index_status ?? "PENDING"} /><CaseStatusBadge value={item.review_status ?? "DRAFT"} />
  </Link>)}</div>}
  <div className="pagination"><button className="button" disabled={page === 0} onClick={() => setCursors((old) => old.slice(0, -1))}>上一页</button><span className="mono">第 {page + 1} 页 · {query.data?.total ?? 0} 条</span><button className="button" disabled={!query.data?.next_cursor} onClick={() => query.data?.next_cursor && setCursors((old) => [...old, query.data.next_cursor ?? null])}>下一页</button></div>
  </>;
}
