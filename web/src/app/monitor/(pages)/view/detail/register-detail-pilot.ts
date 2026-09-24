import { registerPageContextPilot } from '@/components/ai-page-context/pilots';
import { isMonitorViewDetailPath } from './detail.pilot';

registerPageContextPilot({
  test: (pathname) => isMonitorViewDetailPath(pathname),
  load: () => import('./detail.pilot'),
});
