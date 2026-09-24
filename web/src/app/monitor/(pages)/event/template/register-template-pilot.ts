import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => pathname.includes('/monitor/event/template'),
  load: () => import('./template.pilot'),
});
