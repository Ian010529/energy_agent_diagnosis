import type { Metadata } from "next";
import { CaseDetail } from "@/components/cases/case-detail";

export const metadata: Metadata = { title: "案例详情" };
export default async function CasePage({ params }: { params: Promise<{ caseId: string }> }) { const { caseId } = await params; return <CaseDetail caseId={caseId} />; }
