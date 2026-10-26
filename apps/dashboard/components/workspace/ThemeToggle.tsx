"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";
import { getTheme, setTheme, subscribeTheme } from "@/lib/theme";
import { Btn } from "./ui";

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, getTheme, () => "light");
  const dark = theme === "dark";

  return (
    <Btn
      variant="tint"
      size="circle"
      className="shrink-0"
      aria-label="Mode gelap"
      aria-pressed={dark}
      title={dark ? "Aktifkan mode terang" : "Aktifkan mode gelap"}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      {dark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
    </Btn>
  );
}
