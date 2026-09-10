import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/ops-analysis/view/'),
  load: () => import('./dashboard.pilot'),
});
