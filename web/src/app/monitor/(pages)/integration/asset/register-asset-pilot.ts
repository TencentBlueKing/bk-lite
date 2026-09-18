import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/integration/asset'),
  load: () => import('./asset.pilot'),
});
