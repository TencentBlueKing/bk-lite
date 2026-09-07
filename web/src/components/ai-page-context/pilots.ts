import type { AiPageContextPilot } from './types';
import { GENERATED_PAGE_CONTEXT_PILOTS } from './pilots.generated';

/** Codegen pilots plus optional runtime registration via `registerPageContextPilot`. */
export const PAGE_CONTEXT_PILOTS: AiPageContextPilot[] = [...GENERATED_PAGE_CONTEXT_PILOTS];

export function registerPageContextPilot(pilot: AiPageContextPilot): () => void {
  PAGE_CONTEXT_PILOTS.push(pilot);
  return () => {
    const index = PAGE_CONTEXT_PILOTS.indexOf(pilot);
    if (index >= 0) PAGE_CONTEXT_PILOTS.splice(index, 1);
  };
}

/** Codegen prefixes end with `/`; leaf routes like `/ops-analysis/view` do not. */
function pathnameForPilotMatch(pathname: string): string {
  if (!pathname) return pathname;
  return pathname.endsWith('/') ? pathname : `${pathname}/`;
}

export function matchPilots(
  pathname: string,
  pilots: AiPageContextPilot[] = PAGE_CONTEXT_PILOTS,
): AiPageContextPilot[] {
  const normalized = pathnameForPilotMatch(pathname);
  return pilots.filter((pilot) => {
    try {
      return Boolean(pilot.test(normalized));
    } catch {
      return false;
    }
  });
}
