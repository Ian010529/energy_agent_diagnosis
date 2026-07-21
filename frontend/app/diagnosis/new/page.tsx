import type { Metadata } from "next";
import { NewDiagnosis } from "@/components/diagnosis/new-diagnosis";

export const metadata: Metadata = { title: "新建诊断" };
export default function NewDiagnosisPage() { return <NewDiagnosis />; }
