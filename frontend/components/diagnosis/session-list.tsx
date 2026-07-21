"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api/browser-client";
import type { SessionList } from "@/lib/api/types";
import { RequestErrorState, Skeleton, EmptyState } from "@/components/ui/states";
import { RiskBadge, StatusBadge } from "@/components/ui/badges";

const groups: Array<[string, string[]]> = [
  ["待处理", ["INIT", "PLAN_READY"]],
  ["运行中", ["DATA_FETCHING", "EVIDENCE_READY"]],
  ["等待补充", ["NEED_USER_INPUT"]],
  ["待审核", ["DRAFT_READY", "REVIEWING"]],
  ["已完成", ["COMPLETED"]],
  ["失败", ["FAILED"]],
];

export function SessionListView({ compact = false }: { compact?: boolean }) {
  const query = useInfiniteQuery({
    queryKey: ["sessions", "infinite"],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => api<SessionList>(`diagnosis/sessions?limit=100${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  if (query.isLoading) return <Skeleton rows={8} />;
  if (query.error) return <RequestErrorState error={query.error} retry={() => void query.refetch()} />;
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  if (!items.length) return <EmptyState title="暂无诊断任务" detail="从告警或自由问诊开始第一条线程。" />;
  return <div className={compact ? "session-list" : undefined}>
    {groups.map(([label, phases]) => {
      const grouped = items.filter((item) => phases.includes(item.phase));
      if (!grouped.length) return null;
      return <section key={label}>
        <h2 className="section-title" style={{ paddingInline: compact ? ".75rem" : 0 }}>{label} · {grouped.length}</h2>
        <div className={compact ? undefined : "list"}>
          {grouped.map((item) => compact ? <SessionRow key={item.session_id} item={item} /> : (
            <Link className="list-row" href={`/diagnosis/${item.session_id}`} key={item.session_id}>
              <div><div className="row-title">{item.alarm_name || item.final_summary || "自由问诊"}</div><div className="row-subtitle">{item.device_id || "未绑定设备"} · {item.site_id || "未绑定场站"} · 审核 {item.latest_review_status || "未提交"}{item.failure_category ? ` · 降级/失败 ${item.failure_category}` : ""}</div></div>
              <div><div className="row-title mono">{item.session_id}</div><div className="row-subtitle">{new Date(item.updated_at).toLocaleString("zh-CN")}</div></div>
              <RiskBadge value={item.risk_level} />
              <StatusBadge value={item.phase} />
            </Link>
          ))}
        </div>
      </section>;
    })}
    {query.hasNextPage ? <div className="pagination"><button className="button" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>{query.isFetchingNextPage ? "正在加载…" : "加载更多"}</button></div> : null}
  </div>;
}

type SessionItem = SessionList["items"][number];
export function SessionRow({ item, selected = false }: { item: SessionItem; selected?: boolean }) {
  return <Link href={`/diagnosis/${item.session_id}`} className={`session-row ${selected ? "selected" : ""}`}>
    <div style={{ display: "flex", gap: ".5rem", alignItems: "center" }}><span className="row-title">{item.alarm_name || "自由问诊"}</span><StatusBadge value={item.phase} /></div>
    <div className="row-subtitle">{item.device_id || "未绑定设备"} · {new Date(item.updated_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</div>
  </Link>;
}

export function DiagnosisInbox() {
  return <div className="page">
    <header className="page-header"><h1>诊断任务</h1><span className="meta">真实后端会话</span><div className="header-actions"><Link className="button primary" href="/diagnosis/new"><Plus size={16} />新建诊断</Link></div></header>
    <div className="content-scroll"><SessionListView /></div>
  </div>;
}
