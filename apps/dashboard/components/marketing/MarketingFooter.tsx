import Link from "next/link";
import { UmroviaMark } from "@/components/UmroviaMark";
import { BtnLink } from "@/components/workspace/ui";

const FOOTER_LINKS: Array<{ href: string; label: string }> = [
  { href: "#fitur", label: "Fitur" },
  { href: "#modul", label: "Modul" },
  { href: "#mulai", label: "Cara mulai" },
  { href: "/login", label: "Masuk" },
];

/**
 * Footer halaman marketing — mengikuti struktur `footer__top` template:
 * deret atas = logo · kolom tautan · CTA pill hitam (`.btn--secondary`),
 * jarak besar, lalu deret bawah = hak cipta (muted) · kebijakan.
 * Latar putih dengan hairline atas (template: `ui-light`).
 */
export function MarketingFooter() {
  return (
    <footer className="border-t border-black/10 bg-white">
      <div className="mkt-container py-14 md:py-16">
        {/* Deret atas: logo · kolom tautan (mulai kolom-4, ala template) ·
            CTA kanan — grid 12 kolom di desktop, tumpuk di mobile */}
        <div className="flex flex-col items-start gap-10 md:grid md:grid-cols-12 md:items-start">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-2.5 md:col-span-3"
            aria-label="Umrovia — beranda"
          >
            <UmroviaMark className="h-7 w-7" />
            <span className="text-lg font-semibold tracking-[-0.04em]">
              Umrovia
            </span>
          </Link>

          <nav
            className="flex flex-col items-start text--t3-md leading-[1.15] md:col-span-4 md:col-start-4"
            aria-label="Navigasi footer"
          >
            {FOOTER_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="transition-opacity hover:opacity-60"
              >
                {link.label}
              </a>
            ))}
          </nav>

          <BtnLink
            href="/register"
            variant="solid"
            className="md:col-span-3 md:col-start-10 md:justify-self-end"
          >
            Coba gratis
          </BtnLink>
        </div>

        <div className="mt-16 flex flex-col gap-3 text--t3-md md:mt-28 md:flex-row md:items-center md:justify-between">
          <span className="text--color-small">© 2026 Umrovia</span>
          <a
            href="#"
            className="transition-opacity hover:opacity-60"
          >
            Kebijakan Privasi
          </a>
        </div>
      </div>
    </footer>
  );
}
