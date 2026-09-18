import { registerPageContextPilot } from '@/components/ai-page-context/pilots';

const RESERVED = new Set(['slo', 'topology', 'applications']);

registerPageContextPilot({
  test: (pathname) => {
    const match = pathname.match(/\/apm\/services\/([^/]+)\//);
    return Boolean(match && !RESERVED.has(match[1]));
  },
  load: () => import('./service.pilot'),
});
