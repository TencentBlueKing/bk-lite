import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/event/strategy/detail'),
  load: () => import('./strategyDetail.pilot'),
});
