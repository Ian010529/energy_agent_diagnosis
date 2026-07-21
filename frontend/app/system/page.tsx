import type { Metadata } from "next";
import { SystemPage } from "@/components/system/system-status";

export const metadata: Metadata = { title: "系统状态" };
export default function Page() { return <SystemPage />; }
