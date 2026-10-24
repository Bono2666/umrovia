import type { ReactNode } from "react";
import Link from "next/link";
import { MarketingHeader } from "./MarketingHeader";
import { MarketingFooter } from "./MarketingFooter";
import { MarketingSection } from "./MarketingSection";
import { SectionScroller } from "./SectionScroller";
import { RevealText } from "./RevealText";
import { CircleArrow } from "./MarketingBits";

export function MarketingPage({ children, title }: { children: ReactNode; title: string }) {
  return <div data-marketing-page={title} className="contents">
    <SectionScroller />
    <MarketingHeader />
    <main id="konten-utama" className="flex-1">
      {children}
      <MarketingSection className="border-t border-black/10 bg-white" innerClassName="mkt-container py-8">
        <nav aria-label="Breadcrumb" className="flex flex-wrap gap-3 text--t3-sm text-muted">
          <Link href="/" className="hover:text-ink">Beranda</Link><span aria-hidden="true">/</span><span aria-current="page">{title}</span>
        </nav>
      </MarketingSection>
    </main>
    <MarketingFooter />
  </div>;
}

export function PageIntro({ eyebrow, title, description, href, linkLabel, gray = false, children }: {
  eyebrow: string; title: string; description: string; href: string; linkLabel: string; gray?: boolean; children?: ReactNode;
}) {
  return <MarketingSection className={gray ? "bg-[#cdcfd0]" : "bg-white"} innerClassName="mkt-container marketing-intro">
    <RevealText className="text--t3-md">{eyebrow}</RevealText>
    <RevealText as="h1" variant="title" delay={100} className="text--h1 mt-10 max-w-[1050px]">{title}</RevealText>
    {children}
    <div className="marketing-intro__bottom">
      <a href={href} className="marketing-arrow-link group" aria-label={linkLabel}>
        <RevealText as="span" delay={100}>{linkLabel}</RevealText>
        <RevealText as="span" variant="slide" delay={180} className="marketing-arrow-link__arrow" aria-hidden="true">
          <CircleArrow className="marketing-arrow-link__icon" />
        </RevealText>
      </a>
      <RevealText delay={260} className="text--t3-md max-w-[480px] text-ink/65">{description}</RevealText>
    </div>
  </MarketingSection>;
}
