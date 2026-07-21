"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

export function ResizablePanel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>{children}</section>;
}

export function ResponsiveDrawer({ open, onOpenChange, title, children }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; children: React.ReactNode }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.28)", zIndex: 19 }} /><Dialog.Content aria-describedby={undefined} className="panel inspector responsive-drawer" style={{ position: "fixed", inset: "0 0 0 auto", width: "min(25rem, 100vw)", zIndex: 20 }}><div className="panel-header"><Dialog.Title>{title}</Dialog.Title><Dialog.Close className="icon-button" aria-label="关闭" style={{ marginLeft: "auto" }}><X size={17} /></Dialog.Close></div>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>;
}
