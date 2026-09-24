import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/integration/list/detail/configure'),
  load: () => import('./configure.pilot'),
});
