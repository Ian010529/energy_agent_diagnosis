import type { Metadata } from "next";
import { DiagnosisInbox } from "@/components/diagnosis/session-list";

export const metadata: Metadata = { title: "诊断任务" };
export default function DiagnosisPage() { return <DiagnosisInbox />; }
