"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { api, errorMessage } from "@/lib/api/browser-client";
import type { AlarmList, DeviceList, SiteList } from "@/lib/api/types";

const schema = z.object({
  mode: z.enum(["alarm", "chat"]),
  site_id: z.string().optional(),
  device_id: z.string().optional(),
  alarm_id: z.string().optional(),
  message: z.string().max(4000).optional(),
}).superRefine((value, ctx) => {
  if (value.mode === "alarm" && (!value.device_id || !value.alarm_id)) ctx.addIssue({ code: "custom", message: "请选择设备和告警", path: ["alarm_id"] });
  if (value.mode === "chat" && !value.message?.trim()) ctx.addIssue({ code: "custom", message: "请输入问题", path: ["message"] });
});
type FormValue = z.infer<typeof schema>;

export function NewDiagnosis() {
  const router = useRouter();
  const [failure, setFailure] = useState("");
  const { control, register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormValue>({
    resolver: zodResolver(schema), defaultValues: { mode: "alarm" },
  });
  const mode = useWatch({ control, name: "mode" });
  const siteId = useWatch({ control, name: "site_id" });
  const deviceId = useWatch({ control, name: "device_id" });
  const alarmId = useWatch({ control, name: "alarm_id" });
  const sites = useQuery({ queryKey: ["sites"], queryFn: () => api<SiteList>("sites") });
  const devices = useQuery({ queryKey: ["devices", siteId], enabled: mode === "alarm", queryFn: () => api<DeviceList>(`devices?limit=100${siteId ? `&site_id=${encodeURIComponent(siteId)}` : ""}`) });
  const alarms = useQuery({ queryKey: ["alarms", deviceId], enabled: !!deviceId, queryFn: () => api<AlarmList>(`alarms?limit=100&device_id=${encodeURIComponent(deviceId ?? "")}`) });
  const runtime = useQuery({ queryKey: ["runtime"], queryFn: async () => (await fetch("/api/runtime")).json() as Promise<{ role: string }> });
  const readOnly = runtime.data?.role === "viewer";
  const canWrite = runtime.data?.role != null && !readOnly;

  async function submit(value: FormValue) {
    if (!canWrite) return;
    setFailure("");
    try {
      const alarm = alarms.data?.items.find((item) => item.alarm_id === value.alarm_id);
      const created = await api<{ session_id: string }>("diagnosis/sessions", {
        method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(value.mode === "alarm" ? {
          source: "alarm", site_id: value.site_id || undefined, device_id: value.device_id,
          alarm_id: value.alarm_id, alarm_name: alarm?.alarm_name,
        } : { source: "chat" }),
      });
      if (value.mode === "chat" && value.message) {
        sessionStorage.setItem(`energy-initial-message:${created.session_id}`, value.message.trim());
      }
      router.push(`/diagnosis/${created.session_id}`);
    } catch (error) { setFailure(errorMessage(error)); }
  }

  const selectedAlarm = alarms.data?.items.find((item) => item.alarm_id === alarmId);
  return <div className="page">
    <header className="page-header"><Link href="/diagnosis" className="icon-button" aria-label="返回"><ArrowLeft size={17} /></Link><h1>新建诊断</h1></header>
    <div className="content-scroll">
      <form className="form-stack" onSubmit={handleSubmit(submit)}>
        {readOnly ? <div className="banner warning">viewer 为只读角色，不能创建诊断线程。</div> : null}
        <div className="field"><label>诊断入口</label><div style={{ display: "flex", gap: ".5rem" }}>
          <label className="button"><input type="radio" value="alarm" {...register("mode")} /> 告警诊断</label>
          <label className="button"><input type="radio" value="chat" {...register("mode")} /> 自由问诊</label>
        </div></div>
        {mode === "alarm" ? <>
          <div className="field"><label htmlFor="site">场站</label><select id="site" className="input" {...register("site_id")}><option value="">全部场站</option>{sites.data?.items.map((item) => <option key={item.site_id} value={item.site_id}>{item.display_name} · {item.device_count} 台设备</option>)}</select></div>
          <div className="field"><label htmlFor="device">设备</label><select id="device" className="input" {...register("device_id")}><option value="">选择设备</option>{devices.data?.items.map((item) => <option key={item.device_id} value={item.device_id}>{item.device_id} · {item.device_model}</option>)}</select></div>
          <div className="field"><label htmlFor="alarm">告警</label><select id="alarm" className="input" {...register("alarm_id")}><option value="">选择告警</option>{alarms.data?.items.map((item) => <option key={item.alarm_id} value={item.alarm_id}>{item.alarm_name} · {item.alarm_level}</option>)}</select>{errors.alarm_id ? <span role="alert">{errors.alarm_id.message}</span> : null}</div>
          {selectedAlarm ? <div className={`banner ${selectedAlarm.supported ? "" : "warning"}`}><CheckCircle2 size={16} />{selectedAlarm.supported ? `已匹配模板 ${selectedAlarm.template_id} · ${selectedAlarm.template_version}` : "当前告警没有支持模板，后端将按既有路由规则处理。"}</div> : null}
        </> : <div className="field"><label htmlFor="message">描述设备现象或问题</label><textarea id="message" className="input" placeholder="例如：这台 PCS 温度持续升高，优先检查什么？" {...register("message")} />{errors.message ? <span role="alert">{errors.message.message}</span> : null}</div>}
        {failure ? <div className="banner danger" role="alert">{failure}</div> : null}
        <div><button className="button primary" disabled={isSubmitting || !canWrite}>{isSubmitting ? "正在创建…" : "创建诊断线程"}</button></div>
      </form>
    </div>
  </div>;
}
