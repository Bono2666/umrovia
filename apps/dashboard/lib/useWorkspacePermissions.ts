"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, hasPermission, type UserPayload } from "./api";

export function useWorkspacePermissions() {
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const [writableEnvironments, setWritableEnvironments] = useState<string[]>([]);
  useEffect(() => {
    let cancelled = false;
    apiFetch<UserPayload>("/me").then((result) => {
      if (cancelled) return;
      if (!result.ok) { setPermissions([]); return; }
      const me = result.data;
      const membership = me.memberships.find((row) => row.tenant.slug === me.active_tenant_slug)
        ?? me.memberships.find((row) => row.status === "ACTIVE");
      setPermissions(membership?.permissions ?? []);
      setWritableEnvironments(membership?.tenant.writable_environments ?? []);
    });
    return () => { cancelled = true; };
  }, []);
  // Referensi stabil: halaman memakai `can` sebagai dependensi efek pemuatan data;
  // fungsi baru tiap render memicu efek → setState → render tanpa henti.
  const can = useCallback((grant: string) => permissions !== null && hasPermission(permissions, grant), [permissions]);
  const canEditEnvironment = useCallback((environment: string) => writableEnvironments.includes(environment), [writableEnvironments]);
  return { loading: permissions === null, can, canEditEnvironment, writableEnvironments };
}
