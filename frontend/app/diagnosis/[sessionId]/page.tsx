import type { Metadata } from "next";
import { DiagnosisWorkspace } from "@/components/diagnosis/workspace";

export const metadata: Metadata = { title: "诊断线程" };
export default async function SessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return <DiagnosisWorkspace sessionId={sessionId} />;
}
