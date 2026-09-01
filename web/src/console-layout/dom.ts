import type { ConsoleChromeLayout } from './contract';

export const applyConsoleChromeLayout = (layout: ConsoleChromeLayout) => {
  const root = document.documentElement;
  root.classList.toggle('console-layout-app-top', layout === 'app-top');
  root.classList.toggle('console-layout-classic', layout === 'classic');
  root.dataset.consoleLayout = layout;
};

export const getAppliedConsoleChromeLayout = (): ConsoleChromeLayout => {
  if (typeof window === 'undefined') {
    return 'classic';
  }
  return window.__BK_LITE_CONSOLE_LAYOUT__ === 'app-top' ? 'app-top' : 'classic';
};
