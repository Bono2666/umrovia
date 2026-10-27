"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BadgePercent,
  BarChart3,
  Bell,
  Building2,
  ClipboardList,
  CreditCard,
  FileText,
  Handshake,
  Landmark,
  LayoutDashboard,
  LifeBuoy,
  ListOrdered,
  MapPin,
  Package,
  PlaneTakeoff,
  Receipt,
  ShieldCheck,
  Target,
  Users,
  Wallet,
} from "lucide-react";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { LogoutButton } from "@/components/LogoutButton";
import { UmroviaLogo } from "@/components/UmroviaLogo";
import { TrialBanner } from "@/components/workspace/TrialBanner";
import { WorkspaceReveal } from "@/components/workspace/WorkspaceReveal";
import { ThemeToggle } from "@/components/workspace/ThemeToggle";
import { Btn, BtnLink, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
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
      { href: "/dashboard/leads", label: "Leads", permission: "leads.manage", icon: Target },
      { href: "/dashboard/jamaah", label: "Jamaah", permission: "pilgrims.read", icon: Users },
      { href: "/dashboard/paket", label: "Paket", permission: "packages.read", icon: Package },
      {
        href: "/dashboard/keberangkatan",
        label: "Keberangkatan",
        permission: "departures.read",
        icon: PlaneTakeoff,
      },
      { href: "/dashboard/booking", label: "Booking", permission: "bookings.read", icon: ClipboardList },
      { href: "/dashboard/daftar-tunggu", label: "Daftar Tunggu", permission: "bookings.read", icon: ListOrdered },
      { href: "/dashboard/agen", label: "Agen", permission: "agents.read", icon: Handshake },
    ],
  },
  {
    title: "Keuangan",
    items: [
      { href: "/dashboard/invoice", label: "Invoice", permission: "invoices.read", icon: FileText },
      { href: "/dashboard/pembayaran", label: "Pembayaran", permission: "payments.read", icon: CreditCard },
      {
        href: "/dashboard/rekening",
        label: "Kas & Bank",
        permission: "bank_accounts.read",
        icon: Landmark,
      },
      { href: "/dashboard/pengeluaran", label: "Pengeluaran", permission: "expenses.read", icon: Receipt },
      { href: "/dashboard/komisi", label: "Komisi Agen", permission: "commissions.read", icon: BadgePercent },
      { href: "/dashboard/wallet", label: "SaaS Wallet", permission: "wallet.read", icon: Wallet },
    ],
  },
  {
    title: "Dokumen & Laporan",
    items: [
      { href: "/dashboard/manifest", label: "Manifest", permission: "manifest.read", icon: FileText },
      { href: "/dashboard/laporan", label: "Laporan", permission: "reports.read", icon: BarChart3 },
      { href: "/dashboard/notifikasi", label: "Notifikasi", permission: "notifications.read", icon: Bell },
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
      { href: "/dashboard/cabang", label: "Cabang", permission: "branches.read", icon: MapPin },
      { href: "/dashboard/bantuan", label: "Bantuan", icon: LifeBuoy },
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
/** Status tenant → label header. RESTRICTED tetap produksi (charge menunggu saldo). */
const TENANT_STATE: Record<string, { label: string; tone: "neutral" | "success" | "warning" | "danger" }> = {
  TRIAL: { label: "DEMO", tone: "warning" },
  ACTIVE: { label: "PRODUKSI", tone: "success" },
  RESTRICTED: { label: "PRODUKSI", tone: "success" },
  SUSPENDED: { label: "DITANGGUHKAN", tone: "danger" },
  TERMINATED: { label: "DIAKHIRI", tone: "danger" },
  PENDING_EMAIL: { label: "MENYIAPKAN", tone: "neutral" },
  PROVISIONING: { label: "MENYIAPKAN", tone: "neutral" },
};

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
      const mobile = window.matchMedia("(max-width: 639px)");
      window.addEventListener("umrovia-sidebar-change", cb);
      mobile.addEventListener("change", cb);
      return () => {
        window.removeEventListener("umrovia-sidebar-change", cb);
        mobile.removeEventListener("change", cb);
      };
    },
    () => {
      const preference = window.localStorage.getItem("umrovia.sidebar");
      return preference ? preference === "collapsed" : window.matchMedia("(max-width: 639px)").matches;
    },
    () => false,
  );

  const toggleSidebar = useCallback(() => {
    const preference = window.localStorage.getItem("umrovia.sidebar");
    const isCollapsed = preference ? preference === "collapsed" : window.matchMedia("(max-width: 639px)").matches;
    const next = !isCollapsed;
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
      // Staf platform tanpa workspace travel → konsol platform.
      if (!result.data.memberships.some((m) => m.status === "ACTIVE") && result.data.is_platform_staff) {
        router.replace("/platform");
        return;
      }
      // Akun jamaah (tanpa workspace) memakai portal, bukan dashboard staf.
      if (!result.data.memberships.some((m) => m.status === "ACTIVE") && result.data.portal_access_count > 0) {
        router.replace("/portal");
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
      <div className="workspace-shell min-h-screen p-8">
        <LoadingState label="Memuat workspace…" />
      </div>
    );
  }

  if (phase !== "ok" || !me || !active) {
    return (
      <div className="workspace-shell flex min-h-screen items-center justify-center p-8">
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
  const environment = TENANT_STATE[active.tenant.state] ?? { label: active.tenant.state, tone: "neutral" as const };

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
          <Link href="/dashboard" aria-label="Umrovia — dashboard">
            <UmroviaLogo />
          </Link>
          <div className="hidden min-w-0 items-center gap-2 border-l border-border pl-3 sm:flex">
            <span className="max-w-48 truncate text-sm font-semibold" title={active.tenant.display_name}>
              {active.tenant.display_name}
            </span>
            <StatusBadge tone={environment.tone}>{environment.label}</StatusBadge>
            {active.tenant.state === "RESTRICTED" ? (
              <Link href="/dashboard/wallet" title="Ada biaya layanan yang menunggu saldo SaaS Wallet" className="text-xs font-semibold text-warning underline">
                Biaya tertunda
              </Link>
            ) : null}
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
            <ThemeToggle />
            {me.is_platform_staff ? (
              <Link href="/platform" className="hidden text-sm font-semibold text-primary underline sm:inline">Konsol platform</Link>
            ) : null}
            <span className="hidden text-sm text-muted sm:inline">{me.email}</span>
            <LogoutButton />
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar navigasi (sticky, scroll sendiri; bisa collapse jadi rail ikon) */}
        <aside
          className={`fixed left-0 top-14 z-20 -mt-px h-[calc(100vh-3.5rem)] shrink-0 self-start overflow-y-auto border-r border-border bg-surface transition-[width] duration-300 sm:sticky ${
            collapsed ? "w-16 py-2" : "w-60 py-4"
          }`}
        >
          <nav className="flex flex-col gap-4" onClick={(event) => {
            if ((event.target as HTMLElement).closest("a") && window.matchMedia("(max-width: 639px)").matches) {
              window.localStorage.setItem("umrovia.sidebar", "collapsed");
              window.dispatchEvent(new Event("umrovia-sidebar-change"));
            }
          }}>
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
                          title={`${item.label} segera tersedia`}
                        >
                          {icon}
                          {collapsed ? null : (
                            <>
                              <span className="truncate">{item.label}</span>
                              <span className="ml-auto text-[0.6rem] font-semibold uppercase">
                                Segera
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
        <main className="ml-16 min-w-0 flex-1 space-y-4 p-4 sm:ml-0 sm:p-6">
          <TrialBanner
            canConvert={hasPermission(permissions, "trial.convert")}
            onConverted={loadMe}
          />
          {(active.tenant.state === "SUSPENDED" || active.tenant.state === "TERMINATED") && pathname !== "/dashboard/bantuan" ? (
            <section className="card max-w-2xl p-8" role="alert">
              <StatusBadge tone="danger">{environment.label}</StatusBadge>
              <h1 className="mt-3 text-xl font-bold">
                {active.tenant.state === "TERMINATED" ? "Workspace ini telah diakhiri" : "Workspace ini sedang ditangguhkan"}
              </h1>
              <p className="mt-2 text-sm text-muted">
                {active.tenant.state === "TERMINATED"
                  ? "Akses operasional dan portal jamaah ditutup oleh platform Umrovia. Data tetap tersimpan sesuai kebijakan retensi."
                  : "Platform Umrovia menangguhkan akses operasional dan portal jamaah untuk sementara. Data Anda tetap aman dan tidak berubah."}
              </p>
              <p className="mt-2 text-sm text-muted">Hubungi tim Umrovia melalui menu Bantuan untuk informasi dan pemulihan akses.</p>
              <div className="mt-5"><BtnLink href="/dashboard/bantuan">Buka Bantuan</BtnLink></div>
            </section>
          ) : (
            <WorkspaceReveal>{children}</WorkspaceReveal>
          )}
        </main>
      </div>
    </div>
  );
}
