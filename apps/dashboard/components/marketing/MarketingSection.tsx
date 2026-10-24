import type { ComponentPropsWithoutRef } from "react";

type MarketingSectionProps = ComponentPropsWithoutRef<"section"> & {
  innerClassName?: string;
};

/** Separate the scroll position from the template's outgoing parallax layer. */
export function MarketingSection({
  children,
  className = "",
  innerClassName = "",
  ...props
}: MarketingSectionProps) {
  return (
    <section {...props} data-scroll-section className={`mkt-scroll-section ${className}`}>
      <div
        data-parallax-pattern="section-out"
        className={`mkt-scroll-section__inner ${innerClassName}`}
      >
        {children}
      </div>
    </section>
  );
}
