import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/integration/group'),
  load: () => import('./group.pilot'),
});
