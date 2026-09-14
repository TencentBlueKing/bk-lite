import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/alarm/alarms/'),
  load: () => import('./alarms.pilot'),
});
