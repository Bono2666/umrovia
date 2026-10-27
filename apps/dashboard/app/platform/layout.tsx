import { Suspense, type ReactNode } from "react";
import { PlatformShell } from "@/components/platform/PlatformShell";
import { LoadingState } from "@/components/workspace/ui";

/** Konsol platform (S18; target produksi: admin.umrovia.com). Suspense wajib:
 *  shell membaca URL (usePathname/useParams) dan konsol memiliki route dinamis. */
export default function PlatformLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="workspace-shell min-h-screen p-8"><LoadingState label="Memuat konsol platform…" /></div>}>
      <PlatformShell>{children}</PlatformShell>
    </Suspense>
  );
}
