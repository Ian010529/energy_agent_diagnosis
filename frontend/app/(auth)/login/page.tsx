import { Suspense } from "react";
import { LoginForm } from "@/components/auth/login-form";

export default function LoginPage() {
  return <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", width: "100%" }}>
    <Suspense><LoginForm /></Suspense>
  </div>;
}
