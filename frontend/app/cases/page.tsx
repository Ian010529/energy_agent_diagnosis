import type { Metadata } from "next";
import { CaseList } from "@/components/cases/case-list";

export const metadata: Metadata = { title: "案例管理" };
export default function CasesPage() { return <div className="page"><header className="page-header"><h1>案例管理</h1><span className="meta">受审核知识库</span></header><div className="content-scroll"><CaseList /></div></div>; }
