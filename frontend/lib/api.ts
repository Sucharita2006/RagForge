import { useEffect, useState } from "react";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** JSON from the API. A failure says what went wrong and what to do about it. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api${path}`, init);
  } catch {
    throw new Error(
      `Cannot reach the API at ${API_URL}. Start it with "docker compose up" and try again.`,
    );
  }
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : null;
    throw new Error(detail ?? `The API answered ${res.status} for ${path}.`);
  }
  return (await res.json()) as T;
}

export function send<T>(path: string, body: unknown, method = "POST"): Promise<T> {
  return api<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

/** GET `path` on mount and whenever it changes; `reload()` fetches it again.
 *  A null path fetches nothing. The previous data stays on screen until the
 *  new data arrives. */
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null,
    error: null,
    loading: path !== null,
  });
  const [turn, setTurn] = useState(0);

  useEffect(() => {
    if (path === null) return;
    let live = true;
    api<T>(path)
      .then((data) => {
        if (live) setState({ data, error: null, loading: false });
      })
      .catch((err) => {
        if (live) setState((s) => ({ ...s, error: message(err), loading: false }));
      });
    return () => {
      live = false;
    };
  }, [path, turn]);

  return { ...state, reload: () => setTurn((t) => t + 1) };
}
