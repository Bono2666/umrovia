"use client";

import { useEffect, useState } from "react";
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
  return { loading: permissions === null, can: (grant: string) => permissions !== null && hasPermission(permissions, grant), canEditEnvironment: (environment: string) => writableEnvironments.includes(environment), writableEnvironments };
}
