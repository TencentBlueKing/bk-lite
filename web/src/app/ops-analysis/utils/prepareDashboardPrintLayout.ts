const waitForNextPaint = () =>
  new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });

export const DASHBOARD_PREPARE_PRINT_EVENT = 'bk-dashboard-prepare-print';

const applyExpandStyles = (element: HTMLElement) => {
  element.style.overflow = 'visible';
  element.style.height = 'auto';
  element.style.maxHeight = 'none';
  element.style.minHeight = 'fit-content';
  element.style.flex = 'none';

  const computedPosition = window.getComputedStyle(element).position;
  if (computedPosition === 'fixed' || element.style.position === 'fixed') {
    element.style.position = 'relative';
    element.style.inset = 'auto';
    element.style.top = 'auto';
    element.style.right = 'auto';
    element.style.bottom = 'auto';
    element.style.left = 'auto';
    element.style.width = '100%';
  }
};

/**
 * Expand the live render DOM so Chromium page.pdf() paginates full content.
 * Mirrors exportPdf expand rules without cloning or screenshot stitching.
 */
export async function prepareDashboardPrintLayout(
  root: HTMLElement | null = typeof document === 'undefined'
    ? null
    : document.querySelector<HTMLElement>('[data-dashboard-render-root="true"]'),
): Promise<void> {
  if (!root) {
    throw new Error('Dashboard render root not found');
  }

  window.dispatchEvent(
    new CustomEvent(DASHBOARD_PREPARE_PRINT_EVENT, {
      detail: { phase: 'prepare-print' },
    }),
  );

  applyExpandStyles(root);

  const expandElements = Array.from(
    root.querySelectorAll<HTMLElement>('[data-export-expand="true"]'),
  );
  expandElements.forEach(applyExpandStyles);

  const hiddenElements = Array.from(
    root.querySelectorAll<HTMLElement>('[data-export-hidden="true"]'),
  );
  hiddenElements.forEach((element) => {
    element.style.display = 'none';
  });

  root
    .querySelectorAll<HTMLElement>('.grid-stack')
    .forEach(applyExpandStyles);

  let ancestor: HTMLElement | null = root.parentElement;
  while (ancestor) {
    applyExpandStyles(ancestor);
    ancestor = ancestor.parentElement;
  }

  applyExpandStyles(document.documentElement);
  applyExpandStyles(document.body);

  await waitForNextPaint();
  await waitForNextPaint();
}
