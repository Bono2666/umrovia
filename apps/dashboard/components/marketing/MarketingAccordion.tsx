"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { RevealText } from "./RevealText";
import { ArrowGlyph } from "./MarketingBits";

type AccordionItem = { id: string; title: string; description: string };

type MarketingAccordionProps = {
  items: readonly AccordionItem[];
  labelledBy: string;
  idPrefix: string;
  tone?: "light" | "dark";
  onActiveChange?: (index: number | null) => void;
  onHoverChange?: (index: number | null) => void;
  onFocusChange?: (index: number | null) => void;
};

/** Shared interaction and animation for the home modules and pricing FAQ. */
export function MarketingAccordion({
  items, labelledBy, idPrefix, tone = "dark", onActiveChange, onHoverChange, onFocusChange,
}: MarketingAccordionProps) {
  const [active, setActive] = useState<number | null>(null);
  const triggers = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number;
    switch (event.key) {
      case "ArrowDown": next = (index + 1) % items.length; break;
      case "ArrowUp": next = (index - 1 + items.length) % items.length; break;
      case "Home": next = 0; break;
      case "End": next = items.length - 1; break;
      default: return;
    }
    event.preventDefault();
    triggers.current[next]?.focus();
  };

  return <div className={`module-accordion module-accordion--${tone}`} aria-labelledby={labelledBy}>
    {items.map((item, index) => {
      const expanded = active === index;
      const triggerId = `${idPrefix}-trigger-${item.id}`;
      const panelId = `${idPrefix}-panel-${item.id}`;
      return <div key={item.id} className="module-accordion__item">
        <h3 className="text--h3">
          <button
            ref={(element) => { triggers.current[index] = element; }}
            id={triggerId}
            type="button"
            className="module-accordion__trigger"
            aria-expanded={expanded}
            aria-controls={panelId}
            onClick={() => {
              const next = expanded ? null : index;
              setActive(next);
              onActiveChange?.(next);
            }}
            onMouseEnter={() => onHoverChange?.(index)}
            onMouseLeave={() => onHoverChange?.(null)}
            onFocus={() => onFocusChange?.(index)}
            onBlur={() => onFocusChange?.(null)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            <RevealText as="span">{item.title}</RevealText>
            <span className="module-accordion__arrow" aria-hidden="true"><ArrowGlyph /></span>
          </button>
        </h3>
        <div id={panelId} role="region" aria-labelledby={triggerId} aria-hidden={!expanded} inert={!expanded} className="module-accordion__panel" data-expanded={expanded}>
          <div className="module-accordion__clip">
            <RevealText className="module-accordion__description">{item.description}</RevealText>
          </div>
        </div>
      </div>;
    })}
  </div>;
}
