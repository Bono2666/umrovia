import type { Metadata } from "next";
import { themeScript } from "@/lib/theme";
import { geistMono, poppins } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Umrovia — Manajemen Travel Umroh & Haji",
    template: "%s · Umrovia",
  },
  description:
    "Sistem manajemen travel Umroh & Haji: jamaah, booking, DP, manifest, dan laporan dalam satu workspace.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="id"
      suppressHydrationWarning
      className={`${poppins.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
