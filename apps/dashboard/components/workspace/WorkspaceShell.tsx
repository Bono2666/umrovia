"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  Bell,
  Building2,
  ClipboardList,
  CreditCard,
  FileText,
  Landmark,
  LayoutDashboard,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  PlaneTakeoff,
  ShieldCheck,
  Target,
  Users,
  Wallet,
} from "lucide-react";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { LogoutButton } from "@/components/LogoutButton";
import { TrialBanner } from "@/components/workspace/TrialBanner";
import { Btn, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, hasPermission, type UserPayload } from "@/lib/api";

type Phase = "loading" | "unauth" | "no-workspace" | "ok";

type NavItem = {
  href: string;
  label: string;
  soon?: string;
  permission?: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
};

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Ringkasan",
    items: [{ href: "/dashboard", label: "Ringkasan", icon: LayoutDashboard }],
  },
  {
    title: "Operasional",
    items: [
      { href: "/dashboard/leads", label: "Leads", soon: "S09", icon: Target },
      { href: "/dashboard/jamaah", label: "Jamaah", soon: "S07", icon: Users },
      { href: "/dashboard/paket", label: "Paket", soon: "S08", icon: Package },
      { href: "/dashboard/keberangkatan", label: "Keberangkatan", soon: "S08", icon: PlaneTakeoff },
      { href: "/dashboard/booking", label: "Booking", soon: "S09", icon: ClipboardList },
    ],
  },
  {
    title: "Keuangan",
    items: [
      { href: "/dashboard/pembayaran", label: "Pembayaran", soon: "S11", icon: CreditCard },
      {
        href: "/dashboard/rekening",
        label: "Kas & Bank",
        permission: "bank_accounts.read",
        icon: Landmark,
      },
      { href: "/dashboard/wallet", label: "SaaS Wallet", soon: "S12", icon: Wallet },
    ],
  },
  {
    title: "Dokumen & Laporan",
    items: [
      { href: "/dashboard/manifest", label: "Manifest", soon: "S10", icon: FileText },
      { href: "/dashboard/laporan", label: "Laporan", soon: "S17", icon: BarChart3 },
      { href: "/dashboard/notifikasi", label: "Notifikasi", soon: "S16", icon: Bell },
    ],
  },
  {
    title: "Pengaturan",
    items: [
      {
        href: "/dashboard/pengguna",
        label: "Pengguna & Role",
        permission: "memberships.read",
        icon: ShieldCheck,
      },
      {
        href: "/dashboard/profil",
        label: "Profil Travel",
        permission: "tenant.settings.read",
        icon: Building2,
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

  // Sidebar collapse: localStorage sebagai store eksternal (useSyncExternalStore
  // — aman untuk hydration; server snapshot = expanded). Toggle memancarkan
  // event khusus agar render ulang terjadi di tab yang sama.
  const collapsed = useSyncExternalStore(
    (cb) => {
      window.addEventListener("umrovia-sidebar-change", cb);
      return () => window.removeEventListener("umrovia-sidebar-change", cb);
    },
    () => window.localStorage.getItem("umrovia.sidebar") === "collapsed",
    () => false,
  );

  const toggleSidebar = useCallback(() => {
    const next = window.localStorage.getItem("umrovia.sidebar") !== "collapsed";
    window.localStorage.setItem("umrovia.sidebar", next ? "collapsed" : "expanded");
    window.dispatchEvent(new Event("umrovia-sidebar-change"));
  }, []);

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
          <Btn
            variant="tint"
            size="circle"
            onClick={toggleSidebar}
            aria-label={collapsed ? "Buka sidebar" : "Tutup sidebar"}
            aria-expanded={!collapsed}
            className="shrink-0"
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" strokeWidth={1.75} />
            ) : (
              <PanelLeftClose className="h-4 w-4" strokeWidth={1.75} />
            )}
          </Btn>
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
        {/* Sidebar navigasi (sticky, scroll sendiri; bisa collapse jadi rail ikon) */}
        <aside
          className={`sticky top-14 -mt-px h-[calc(100vh-3.5rem)] shrink-0 self-start overflow-y-auto border-r border-border bg-surface transition-[width] duration-300 ${
            collapsed ? "w-16 p-2" : "w-60 p-4"
          }`}
        >
          <nav className="flex flex-col gap-4">
            {NAV_GROUPS.map((group) => {
              const items = group.items.filter(
                (item) => !item.permission || hasPermission(permissions, item.permission),
              );
              if (items.length === 0) return null;
              return (
                <div key={group.title}>
                  {collapsed ? (
                    <div className="mx-1 border-t border-border" />
                  ) : (
                    <p className="px-2 text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
                      {group.title}
                    </p>
                  )}
                  <div className="mt-1 flex flex-col gap-0.5">
                    {items.map((item) => {
                      const Icon = item.icon;
                      const icon = (
                        <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
                      );
                      const center = collapsed ? "justify-center" : "";
                      return item.soon ? (
                        <span
                          key={item.href}
                          className={`flex items-center gap-2 px-2 py-1.5 text-sm text-muted/60 ${center}`}
                          title={
                            collapsed
                              ? `${item.label} — menyusul ${item.soon}`
                              : `Modul ${item.label} menyusul ${item.soon}`
                          }
                        >
                          {icon}
                          {collapsed ? null : (
                            <>
                              <span className="truncate">{item.label}</span>
                              <span className="ml-auto text-[0.6rem] font-semibold">
                                {item.soon}+
                              </span>
                            </>
                          )}
                        </span>
                      ) : (
                        <Link
                          key={item.href}
                          href={item.href}
                          title={item.label}
                          className={`flex items-center gap-2 px-2 py-1.5 text-sm font-medium ${center} ${
                            pathname === item.href
                              ? "bg-primary/10 text-primary"
                              : "text-ink hover:bg-background"
                          }`}
                        >
                          {icon}
                          {collapsed ? null : <span className="truncate">{item.label}</span>}
                        </Link>
                      );
                    })}
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
