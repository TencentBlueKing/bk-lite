import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/search'),
  load: () => import('./search.pilot'),
});
