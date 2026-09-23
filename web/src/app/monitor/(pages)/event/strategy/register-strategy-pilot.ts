import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/event/strategy/') && !pathname.includes('/detail'),
  load: () => import('./strategy.pilot'),
});
