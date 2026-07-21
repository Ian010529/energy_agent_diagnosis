"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Search, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const commands = [
  ["新建诊断", "/diagnosis/new"],
  ["诊断任务", "/diagnosis"],
  ["人工审核", "/reviews"],
  ["案例管理", "/cases"],
  ["系统状态", "/system"],
] as const;

export function CommandMenu() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const visible = commands.filter(([label]) => label.includes(query.trim()));
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger asChild><button className="command-trigger" aria-label="打开命令菜单"><Search size={15} /> <span>搜索</span><kbd>⌘K</kbd></button></Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="command-menu" aria-describedby={undefined}>
      <Dialog.Title>快速导航</Dialog.Title><Dialog.Close className="icon-button" aria-label="关闭命令菜单"><X size={16} /></Dialog.Close>
      <input autoFocus className="input" aria-label="搜索命令" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入页面名称…" />
      <div className="command-results">{visible.map(([label, href]) => <button key={href} onClick={() => { setOpen(false); router.push(href); }}>{label}<span>{href}</span></button>)}</div>
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>;
}
