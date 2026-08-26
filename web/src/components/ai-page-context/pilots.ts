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

export function matchPilots(
  pathname: string,
  pilots: AiPageContextPilot[] = PAGE_CONTEXT_PILOTS,
): AiPageContextPilot[] {
  return pilots.filter((pilot) => {
    try {
      return Boolean(pilot.test(pathname));
    } catch {
      return false;
    }
  });
}
