import type { AiPageContextPilot } from './types';

export const PAGE_CONTEXT_PILOTS: AiPageContextPilot[] = [
  {
    test: (pathname) => pathname.includes('/monitor/view/dashboard/'),
    load: () => import('@/app/monitor/(pages)/view/dashboard/dashboard.pilot'),
  },
];

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
