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
  PlaneTakeoff,
  ShieldCheck,
  Target,
  Users,
  Wallet,
} from "lucide-react";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { LogoutButton } from "@/components/LogoutButton";
import { UmroviaMark } from "@/components/UmroviaMark";
import { TrialBanner } from "@/components/workspace/TrialBanner";
import { Btn, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, hasPermission, type UserPayload } from "@/lib/api";

type Phase = "loading" | "unauth" | "no-workspace" | "ok";

type NavItem = {
  href: string;
  label: string;
  soon?: string;
  permission?: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
};

/**
 * Icon panah toggle sidebar — path persis icon mega menu web_template
 * (`icons.svg#arrow-down-small`: viewBox 10×10, stroke currentColor 1.2;
 * dirender 12×12 agar pas dengan kotak isi `btn--circle-xs`).
 * Arah disesuaikan: sidebar terbuka → panah ke kiri (aksi tutup),
 * sidebar tertutup → panah ke kanan (aksi buka). Berputar 180° saat status
 * berubah lewat KLIK (bukan hover seperti template) dengan easing
 * editorial .6s; transisi hanya diaktifkan setelah klik pertama (`animate`)
 * agar panah tidak ikut berputar saat hydration.
 */
function CollapseArrow({
  collapsed,
  animate,
}: {
  collapsed: boolean;
  animate: boolean;
}) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 10 10"
      aria-hidden="true"
      className={[
        collapsed ? "-rotate-90" : "rotate-90",
        animate
          ? "transition-transform duration-[600ms] ease-[cubic-bezier(.25,.74,.22,.99)] motion-reduce:transition-none"
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        d="M9 5 5 9m0 0L1 5m4 4V1"
      />
    </svg>
  );
}

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Ringkasan",
    items: [{ href: "/dashboard", label: "Ringkasan", icon: LayoutDashboard }],
  },
  {
    title: "Operasional",
    items: [
      { href: "/dashboard/leads", label: "Leads", soon: "P1", icon: Target },
      { href: "/dashboard/jamaah", label: "Jamaah", permission: "pilgrims.read", icon: Users },
      { href: "/dashboard/paket", label: "Paket", permission: "packages.read", icon: Package },
      {
        href: "/dashboard/keberangkatan",
        label: "Keberangkatan",
        permission: "departures.read",
        icon: PlaneTakeoff,
      },
      { href: "/dashboard/booking", label: "Booking", permission: "bookings.read", icon: ClipboardList },
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
      { href: "/dashboard/manifest", label: "Manifest", permission: "manifest.read", icon: FileText },
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
  // Transisi putar icon toggle baru diaktifkan setelah klik pertama —
  // mencegah panah ikut berputar saat hydration (sidebar tersimpan
  // collapsed di localStorage, server snapshot = expanded).
  const [arrowReady, setArrowReady] = useState(false);

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
    setArrowReady(true);
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
    <div className="workspace-shell min-h-screen">
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
            <CollapseArrow collapsed={collapsed} animate={arrowReady} />
          </Btn>
          <Link
            href="/dashboard"
            className="flex items-center gap-2 text-lg font-semibold tracking-tight text-ink"
          >
            <UmroviaMark className="h-7 w-7 shrink-0" />
            Umrovia<span className="text-primary">.</span>
          </Link>
          <div className="flex items-center gap-2 border-l border-border pl-3">
            <span className="max-w-48 truncate text-sm font-semibold" title={active.tenant.display_name}>
              {active.tenant.display_name}
            </span>
            <StatusBadge tone={environment.tone}>{environment.label}</StatusBadge>
          </div>
          {activeList.length > 1 ? (
            <FormSelect
              htmlFor="workspace-switcher"
              className="w-auto pb-1 text-sm"
              value={active.tenant.slug}
              onChange={(event) => onSwitch(event.target.value)}
              aria-label="Pindah workspace"
            >
              {activeList.map((m) => (
                <option key={m.tenant.id} value={m.tenant.slug}>
                  {m.tenant.display_name}
                </option>
              ))}
            </FormSelect>
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
            collapsed ? "w-16 py-2" : "w-60 py-4"
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
                    <div className="mx-3 border-t border-border" />
                  ) : (
                    <p className="px-6 text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
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
                      const inset = collapsed ? "px-2" : "px-6";
                      const isActive = pathname === item.href;
                      /* Roll teks menu — replika hover menu web_template
                         (`.btn--cloned .btn__content`): label diduplikasi di
                         bawah lapisan `overflow:hidden`, keduanya berguling
                         naik -100% saat hover (0.6s editorial). */
                      const roll =
                        "block truncate transition-transform duration-[600ms] ease-[cubic-bezier(.25,.74,.22,.99)] group-hover:-translate-y-full motion-reduce:transition-none";
                      return item.soon ? (
                        <span
                          key={item.href}
                          className={`flex w-full items-center gap-2 py-1.5 text-sm text-muted/60 ${inset} ${center}`}
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
                          aria-current={isActive ? "page" : undefined}
                          className={`group flex w-full items-center gap-2 py-1.5 text-sm font-medium ${inset} ${center} ${
                            isActive
                              ? "text-primary"
                              : "text-ink hover:bg-background"
                          }`}
                        >
                          {icon}
                          {collapsed ? null : (
                            <span className="relative block min-w-0 overflow-hidden">
                              <span className={roll}>{item.label}</span>
                              <span
                                aria-hidden
                                className={`absolute left-0 top-full w-full ${roll}`}
                              >
                                {item.label}
                              </span>
                            </span>
                          )}
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
        <main className="min-w-0 flex-1 space-y-4 p-4 sm:p-6">
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
