import type { ReactNode } from "react";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";

/**
 * App shell workspace travel (app.umrovia.com) — S06: guard auth + tenant
 * header + sidebar lengkap pindah ke WorkspaceShell (client, Spec §4.1).
 */
export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return <WorkspaceShell>{children}</WorkspaceShell>;
}
