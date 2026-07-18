"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiOffline, firstTenant, type Tenant } from "./api";

interface ApiState<T> {
  data: T | null;
  tenant: Tenant | null;
  loading: boolean;
  offline: boolean;
  error: string | null;
}

/** Resolve the demo tenant, then load page data. Never throws into render:
 *  offline -> { offline: true } so pages show the full-page offline panel. */
export function useApi<T>(
  load: (tenant: Tenant) => Promise<T>,
  deps: readonly unknown[] = [],
): ApiState<T> & { retry: () => void } {
  const [state, setState] = useState<ApiState<T>>({
    data: null,
    tenant: null,
    loading: true,
    offline: false,
    error: null,
  });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let alive = true;
    // no sync setState here (react-hooks/set-state-in-effect): on dep change
    // the previous data stays visible until the new fetch resolves.
    (async () => {
      try {
        const tenant = await firstTenant();
        if (!tenant) {
          if (alive)
            setState({ data: null, tenant: null, loading: false, offline: false, error: "no tenants" });
          return;
        }
        const data = await load(tenant);
        if (alive) setState({ data, tenant, loading: false, offline: false, error: null });
      } catch (e) {
        if (!alive) return;
        if (e instanceof ApiOffline) {
          setState({ data: null, tenant: null, loading: false, offline: true, error: null });
        } else {
          setState({
            data: null,
            tenant: null,
            loading: false,
            offline: false,
            error: e instanceof Error ? e.message : String(e),
          });
        }
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt, ...deps]);

  return { ...state, retry };
}
