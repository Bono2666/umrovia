import Link from "next/link";
import type { ReactNode } from "react";
import { LogoutButton } from "@/components/LogoutButton";

const NAV = [
  { href: "/dashboard", label: "Ringkasan" },
  { href: "/dashboard/paket", label: "Paket" },
  { href: "/dashboard/keberangkatan", label: "Keberangkatan" },
  { href: "/dashboard/jamaah", label: "Jamaah" },
  { href: "/dashboard/booking", label: "Booking" },
  { href: "/dashboard/pembayaran", label: "Pembayaran" },
  { href: "/dashboard/manifest", label: "Manifest" },
  { href: "/dashboard/laporan", label: "Laporan" },
];

/**
 * App shell workspace travel (app.umrovia.com) — S01 skeleton.
 * Tenant banner & RBAC menu penuh menyusul di S05–S06 (Spec §4.1 navigasi).
 */
export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface p-4">
        <div className="text-lg font-bold text-primary">Umrovia</div>
        <div className="mt-1 text-xs text-muted">Workspace travel</div>
        <nav className="mt-6 flex flex-col gap-1">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded px-3 py-2 text-sm font-medium text-ink hover:bg-background"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto text-xs text-muted">
          Pay-per-jamaah · Rp50.000 / jamaah
        </div>
      </aside>
      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-surface px-6 py-3">
          <div className="text-sm text-muted">
            {/* Tenant banner: nama travel + environment (DEMO/PRODUKSI) — S05 */}
            <span className="font-semibold text-ink">Umrovia</span> · workspace
          </div>
          <LogoutButton />
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
