"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { LogoutButton } from "@/components/LogoutButton";
import { TrialBanner } from "@/components/workspace/TrialBanner";
import { LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, hasPermission, type UserPayload } from "@/lib/api";

type Phase = "loading" | "unauth" | "no-workspace" | "ok";

type NavItem = {
  href: string;
  label: string;
  soon?: string;
  permission?: string;
};

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Ringkasan",
    items: [{ href: "/dashboard", label: "Ringkasan" }],
  },
  {
    title: "Operasional",
    items: [
      { href: "/dashboard/leads", label: "Leads", soon: "S09" },
      { href: "/dashboard/jamaah", label: "Jamaah", soon: "S07" },
      { href: "/dashboard/paket", label: "Paket", soon: "S08" },
      { href: "/dashboard/keberangkatan", label: "Keberangkatan", soon: "S08" },
      { href: "/dashboard/booking", label: "Booking", soon: "S09" },
    ],
  },
  {
    title: "Keuangan",
    items: [
      { href: "/dashboard/pembayaran", label: "Pembayaran", soon: "S11" },
      {
        href: "/dashboard/rekening",
        label: "Kas & Bank",
        permission: "bank_accounts.read",
      },
      { href: "/dashboard/wallet", label: "SaaS Wallet", soon: "S12" },
    ],
  },
  {
    title: "Dokumen & Laporan",
    items: [
      { href: "/dashboard/manifest", label: "Manifest", soon: "S10" },
      { href: "/dashboard/laporan", label: "Laporan", soon: "S17" },
      { href: "/dashboard/notifikasi", label: "Notifikasi", soon: "S16" },
    ],
  },
  {
    title: "Pengaturan",
    items: [
      {
        href: "/dashboard/pengguna",
        label: "Pengguna & Role",
        permission: "memberships.read",
      },
      {
        href: "/dashboard/profil",
        label: "Profil Travel",
        permission: "tenant.settings.read",
      },
    ],
  },
];

/**
 * Shell workspace travel (S06, Spec §4.1): guard auth (redirect /login bila
 * sesi berakhir), header nama workspace + badge lingkungan teks
 * DEMO/PRODUCTION (§4.3), pemilih workspace bila >1 membership, sidebar
 * lengkap (menu modul menyusul ditandai), banner trial, dan blok konten.
 *
 * Permission klien hanya untuk UX; server tetap otoritas (semua endpoint
 * menegakkan permission + tenant context sendiri).
 */
export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<UserPayload | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [switchError, setSwitchError] = useState<string | null>(null);

  const loadMe = useCallback(() => {
    apiFetch<UserPayload>("/me").then((result) => {
      if (!result.ok) {
        if (result.error.status === 401 || result.error.status === 403) {
          setPhase("unauth");
          router.replace("/login");
          return;
        }
        setPhase("unauth");
        return;
      }
      setMe(result.data);
      setPhase("ok");
    });
  }, [router]);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  // Resolusi workspace aktif — mirror fallback server (sesi switch, atau
  // membership ACTIVE pertama; Spec §8.1 /workspaces/switch).
  const active =
    me?.memberships.find((m) => m.tenant.slug === (me.active_tenant_slug ?? "")) ??
    me?.memberships.find((m) => m.status === "ACTIVE");
  const activeList =
    me?.memberships.filter((m) => m.status === "ACTIVE") ?? [];

  if (phase === "loading") {
    return (
      <div className="p-8">
        <LoadingState label="Memuat workspace…" />
      </div>
    );
  }

  if (phase !== "ok" || !me || !active) {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <div className="card max-w-md p-8 text-center">
          <p className="font-semibold">Tidak ada workspace aktif</p>
          <p className="mt-2 text-sm text-muted">
            Akun ini tidak memiliki membership aktif di workspace mana pun.
            Minta Owner mengundang ulang, atau hubungi support.
          </p>
          <div className="mt-4 flex justify-center">
            <LogoutButton />
          </div>
        </div>
      </div>
    );
  }

  const permissions = active.permissions;
  const environment =
    active.tenant.state === "TRIAL"
      ? { label: "DEMO", tone: "warning" as const }
      : active.tenant.state === "ACTIVE"
        ? { label: "PRODUCTION", tone: "success" as const }
        : { label: active.tenant.state, tone: "neutral" as const };

  async function onSwitch(slug: string) {
    if (!slug || slug === active?.tenant.slug) return;
    setSwitchError(null);
    const result = await apiFetch<{ active: unknown }>("/workspaces/switch", {
      method: "POST",
      body: JSON.stringify({ slug }),
    });
    if (!result.ok) {
      setSwitchError(result.error.detail || "Gagal berpindah workspace.");
      return;
    }
    loadMe();
  }

  return (
    <div className="min-h-screen">
      {/* Navbar atas (sticky): identitas brand + konteks workspace + akun/keluar */}
      <header className="sticky top-0 z-30 border-b border-border bg-surface">
        <div className="flex h-14 items-center gap-3 px-4">
          <Link
            href="/dashboard"
            className="text-lg font-semibold tracking-tight text-ink"
          >
            Umrovia<span className="text-primary">.</span>
          </Link>
          <div className="flex items-center gap-2 border-l border-border pl-3">
            <span className="max-w-48 truncate text-sm font-semibold" title={active.tenant.display_name}>
              {active.tenant.display_name}
            </span>
            <StatusBadge tone={environment.tone}>{environment.label}</StatusBadge>
          </div>
          {activeList.length > 1 ? (
            <select
              className="input w-auto text-sm"
              value={active.tenant.slug}
              onChange={(event) => onSwitch(event.target.value)}
              aria-label="Pindah workspace"
            >
              {activeList.map((m) => (
                <option key={m.tenant.id} value={m.tenant.slug}>
                  {m.tenant.display_name}
                </option>
              ))}
            </select>
          ) : null}
          {switchError ? (
            <span className="text-xs text-danger" role="alert">
              {switchError}
            </span>
          ) : null}
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-sm text-muted sm:inline">{me.email}</span>
            <LogoutButton />
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar navigasi (sticky, scroll sendiri): tinggi = viewport − navbar */}
        <aside className="sticky top-14 -mt-px h-[calc(100vh-3.5rem)] w-60 shrink-0 self-start overflow-y-auto border-r border-border bg-surface p-4">
          <nav className="flex flex-col gap-4">
            {NAV_GROUPS.map((group) => {
              const items = group.items.filter(
                (item) => !item.permission || hasPermission(permissions, item.permission),
              );
              if (items.length === 0) return null;
              return (
                <div key={group.title}>
                  <p className="px-2 text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
                    {group.title}
                  </p>
                  <div className="mt-1 flex flex-col gap-0.5">
                    {items.map((item) =>
                      item.soon ? (
                        <span
                          key={item.href}
                          className="flex items-center justify-between px-2 py-1.5 text-sm text-muted/60"
                          title={`Modul ${item.label} menyusul ${item.soon}`}
                        >
                          {item.label}
                          <span className="text-[0.6rem] font-semibold">{item.soon}+</span>
                        </span>
                      ) : (
                        <Link
                          key={item.href}
                          href={item.href}
                          className={`px-2 py-1.5 text-sm font-medium ${
                            pathname === item.href
                              ? "bg-primary/10 text-primary"
                              : "text-ink hover:bg-background"
                          }`}
                        >
                          {item.label}
                        </Link>
                      ),
                    )}
                  </div>
                </div>
              );
            })}
          </nav>
        </aside>

        {/* Konten halaman */}
        <main className="min-w-0 flex-1 space-y-4 p-6">
          <TrialBanner
            canConvert={hasPermission(permissions, "trial.convert")}
            onConverted={loadMe}
          />
          {children}
        </main>
      </div>
    </div>
  );
}
