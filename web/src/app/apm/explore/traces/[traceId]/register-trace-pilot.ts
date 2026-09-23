import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

registerPageContextPilot({
  test: (pathname) => /\/apm\/explore\/traces\/[^/]+\//.test(pathname),
  load: () => import('./trace.pilot'),
});
