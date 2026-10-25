export type Theme = "light" | "dark";

export const THEME_KEY = "umrovia.theme";
const THEME_EVENT = "umrovia-theme-change";
const SYSTEM_THEME = "(prefers-color-scheme: dark)";
let sessionTheme: Theme | undefined;

export function getTheme(): Theme {
  if (sessionTheme) return sessionTheme;
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // Theme switching remains available when browser storage is blocked.
  }
  return window.matchMedia(SYSTEM_THEME).matches ? "dark" : "light";
}

export function setTheme(theme: Theme) {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
    sessionTheme = undefined;
  } catch {
    sessionTheme = theme;
  }
  document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new Event(THEME_EVENT));
}

export function subscribeTheme(onChange: () => void) {
  const media = window.matchMedia(SYSTEM_THEME);
  const sync = () => {
    document.documentElement.dataset.theme = getTheme();
    onChange();
  };
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_KEY || event.key === null) sync();
  };
  window.addEventListener(THEME_EVENT, sync);
  window.addEventListener("storage", onStorage);
  media.addEventListener("change", sync);
  sync();
  return () => {
    window.removeEventListener(THEME_EVENT, sync);
    window.removeEventListener("storage", onStorage);
    media.removeEventListener("change", sync);
  };
}

// Runs before the first paint so a saved dark theme never flashes light.
export const themeScript = `(() => {
  let theme;
  try { theme = localStorage.getItem(${JSON.stringify(THEME_KEY)}); } catch {}
  document.documentElement.dataset.theme = theme === "light" || theme === "dark"
    ? theme : matchMedia(${JSON.stringify(SYSTEM_THEME)}).matches ? "dark" : "light";
})();`;
