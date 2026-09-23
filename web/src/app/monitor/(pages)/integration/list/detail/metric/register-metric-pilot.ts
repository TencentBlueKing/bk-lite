import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/integration/list/detail/metric'),
  load: () => import('./metric.pilot'),
});
