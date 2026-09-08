const inflight = new Map<string, Promise<unknown>>();

export function resetAppCapabilityCache() {
  inflight.clear();
}

export async function loadAuthorizedCapability<T>(
  appName: string,
  options: {
    authorized: boolean;
    load: () => Promise<T>;
  }
): Promise<T | null> {
  if (!options.authorized) {
    return null;
  }

  const cached = inflight.get(appName);
  if (cached) {
    return cached as Promise<T | null>;
  }

  const pending = options
    .load()
    .catch(() => null)
    .then((mod) => mod);
  inflight.set(appName, pending);
  return pending as Promise<T | null>;
}
