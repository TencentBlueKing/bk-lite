import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/integration/list/detail/collect'),
  load: () => import('./collect.pilot'),
});
