import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/alarm/incidents/'),
  load: () => import('./incidents.pilot'),
});
