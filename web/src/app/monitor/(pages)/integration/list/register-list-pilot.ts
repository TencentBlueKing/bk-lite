import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/integration/list') && !pathname.includes('/detail'),
  load: () => import('./list.pilot'),
});
