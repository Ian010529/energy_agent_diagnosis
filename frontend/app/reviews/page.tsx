import type { Metadata } from "next";
import { ReviewsWorkspace } from "@/components/reviews/review-panel";

export const metadata: Metadata = { title: "人工审核" };
export default function ReviewsPage() { return <ReviewsWorkspace />; }
