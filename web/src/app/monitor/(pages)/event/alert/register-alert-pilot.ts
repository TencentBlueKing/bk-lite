import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/event/alert/'),
  load: () => import('./alert.pilot'),
});
