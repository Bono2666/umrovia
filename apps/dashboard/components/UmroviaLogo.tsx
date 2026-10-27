import { UmroviaMark } from "@/components/UmroviaMark";

type UmroviaLogoProps = {
  /** Warna & tata letak tambahan; bawaan hijau brand. Kosongkan ("") agar mewarisi warna induk (header marketing berganti nada). */
  className?: string;
};

/**
 * Logo resmi Umrovia — monogram "um" + wordmark "Umrovia", identik dengan
 * header/footer halaman marketing (Poppins 600, tracking -0.04em, jarak 2.5).
 * Dipakai di semua permukaan (marketing, dashboard, portal, konsol, login)
 * agar brand tidak menyimpang antar-halaman.
 */
export function UmroviaLogo({ className = "text-primary" }: UmroviaLogoProps) {
  return (
    <span className={`flex shrink-0 items-center gap-2.5 ${className}`}>
      <UmroviaMark className="h-7 w-7 shrink-0" />
      <span className="text-lg font-semibold tracking-[-0.04em]">Umrovia</span>
    </span>
  );
}
