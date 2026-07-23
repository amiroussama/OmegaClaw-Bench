import { useEffect, useState } from "react";
import type { Catalog, RunDetail } from "./schema";

const BASE = import.meta.env.BASE_URL; // e.g. "./" — data lives at <base>data/*

const cache = new Map<string, unknown>();

async function getJson<T>(rel: string): Promise<T> {
  const url = `${BASE}data/${rel}`;
  if (cache.has(url)) return cache.get(url) as T;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} fetching ${rel}`);
  const j = (await res.json()) as T;
  cache.set(url, j);
  return j;
}

type Async<T> = { data: T | null; error: string | null; loading: boolean };

function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): Async<T> {
  const [state, setState] = useState<Async<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    let live = true;
    setState({ data: null, error: null, loading: true });
    fn()
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((e) => live && setState({ data: null, error: String(e?.message ?? e), loading: false }));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function useCatalog(): Async<Catalog> {
  return useAsync<Catalog>(() => getJson<Catalog>("index.json"), []);
}

export function useRunDetail(detail: string | null | undefined): Async<RunDetail> {
  return useAsync<RunDetail>(async () => {
    if (!detail) throw new Error("no run selected");
    return getJson<RunDetail>(detail);
  }, [detail]);
}
