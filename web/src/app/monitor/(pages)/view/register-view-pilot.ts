import { registerPageContextPilot } from '@/components/ai-page-context/pilots';
import { isMonitorViewIndexPath } from './view.pilot';

registerPageContextPilot({
  test: (pathname) => isMonitorViewIndexPath(pathname),
  load: () => import('./view.pilot'),
});
