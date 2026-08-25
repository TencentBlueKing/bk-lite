import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/view/dashboard/'),
  load: () => import('./dashboard.pilot'),
});
