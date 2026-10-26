"use client";

import {
  Children,
  cloneElement,
  isValidElement,
  useEffect,
  useRef,
  type CSSProperties,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";

type RevealTextProps = HTMLAttributes<HTMLElement> & {
  as?: "h1" | "h2" | "h3" | "p" | "span";
  variant?: "title" | "text" | "slide";
  delay?: number;
};

/** Render the split text with React, not innerHTML, so hydration and cached
 * routes keep ownership of their DOM. Children must be non-interactive copy. */
function splitContent(children: ReactNode, variant: "title" | "text"): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child === "string" || typeof child === "number") {
      return String(child).split(/(\s+)/).map((word, index) => {
        if (!word.trim()) return word;
        return <span key={index} className="mkt-text-reveal__word">
          {variant === "title"
            ? Array.from(word, (char, charIndex) => <span key={charIndex} className="mkt-text-reveal__unit">{char}</span>)
            : <span className="mkt-text-reveal__unit">{word}</span>}
        </span>;
      });
    }
    if (isValidElement<{ children?: ReactNode }>(child) && child.type !== "br") {
      return cloneElement(child, undefined, splitContent(child.props.children, variant));
    }
    return child;
  });
}

/** web_template's title: 750ms, masked characters moving up 110%.
 * Its text: 700ms, 40ms stagger per measured line, moving up 150%.
 * Slide treats decorative content (such as an arrow) as one reveal unit.
 * Reveal once on entry; small screens/reduced motion retain static text. */
export function RevealText({
  as: Tag = "p", variant = "text", delay = 30, className = "", style, children, ...props
}: RevealTextProps) {
  const root = useRef<HTMLHeadingElement>(null);
  const pathname = usePathname();

  useEffect(() => {
    const element = root.current;
    if (!element) return;
    const screen = window.matchMedia("(min-width: 568px) and (max-aspect-ratio: 13/9), (min-width: 668px) and (min-height: 416px), (min-width: 980px)");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce), (update: slow)");
    let stop: (() => void) | undefined;
    // Once revealed, a media change (resize/rotation) must not hide the text again.
    let revealed = false;
    const updateMode = () => {
      stop?.();
      stop = undefined;
      if (!screen.matches || reduced.matches) return;

      let disposed = false;
      let frame = 0;
      const words = Array.from(element.querySelectorAll<HTMLElement>(".mkt-text-reveal__word"));
      const measureLines = () => {
        let previousTop = -Infinity;
        let line = -1;
        for (const word of words) {
          const top = word.offsetTop;
          if (Math.abs(top - previousTop) > 2) line++;
          word.style.setProperty("--text-reveal-line", String(line));
          previousTop = top;
        }
      };
      measureLines();
      element.dataset.revealReady = "true";
      if (revealed) element.dataset.revealVisible = "true";
      const observer = new IntersectionObserver((entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        element.dataset.revealVisible = "true";
        revealed = true;
        observer.disconnect();
      }, { rootMargin: "0px 0px -100px 0px", threshold: 0 });
      const resize = new ResizeObserver(measureLines);
      resize.observe(element);
      // Allow the hidden pose to paint before starting an in-view transition.
      if (!revealed) frame = requestAnimationFrame(() => observer.observe(element));
      document.fonts.ready.then(() => {
        if (!disposed) measureLines();
      }).catch(() => {});
      stop = () => {
        disposed = true;
        cancelAnimationFrame(frame);
        observer.disconnect();
        resize.disconnect();
        delete element.dataset.revealReady;
        delete element.dataset.revealVisible;
        words.forEach((word) => word.style.removeProperty("--text-reveal-line"));
      };
    };
    updateMode();
    screen.addEventListener("change", updateMode);
    reduced.addEventListener("change", updateMode);
    return () => {
      screen.removeEventListener("change", updateMode);
      reduced.removeEventListener("change", updateMode);
      stop?.();
    };
  }, [pathname, variant, children]);

  return <Tag
    {...props}
    ref={root}
    className={`mkt-text-reveal mkt-text-reveal--${variant} ${className}`}
    style={{ ...style, "--text-reveal-delay": `${delay}ms` } as CSSProperties}
  >
    <span className="sr-only select-none">{children}</span>
    <span aria-hidden="true" data-reveal-visual>
      {variant === "slide"
        ? <span className="mkt-text-reveal__unit">{children}</span>
        : splitContent(children, variant)}
    </span>
  </Tag>;
}
