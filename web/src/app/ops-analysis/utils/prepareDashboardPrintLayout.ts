const waitForNextPaint = () =>
  new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });

export const DASHBOARD_PREPARE_PRINT_EVENT = 'bk-dashboard-prepare-print';

const waitForImageDecode = (image: HTMLImageElement) => {
  if (typeof image.decode !== 'function') {
    return Promise.resolve();
  }
  return image.decode().catch(() => undefined);
};

const isWebGLCanvas = (canvas: HTMLCanvasElement): boolean => {
  try {
    return Boolean(canvas.getContext('webgl') || canvas.getContext('webgl2'));
  } catch {
    return false;
  }
};

/**
 * Chromium page.pdf() 不会把 WebGL 画进印刷层。打印前只把 WebGL canvas 冻成 img。
 */
export const snapshotCanvasesForPrint = async (
  root: HTMLElement,
): Promise<void> => {
  const canvases = Array.from(root.querySelectorAll('canvas'));
  const images: HTMLImageElement[] = [];

  canvases.forEach((canvas) => {
    if (canvas.dataset.printSnapshot === 'replaced') {
      return;
    }
    if (canvas.width === 0 || canvas.height === 0) {
      return;
    }
    if (!isWebGLCanvas(canvas)) {
      return;
    }

    let dataUrl = '';
    try {
      dataUrl = canvas.toDataURL('image/png');
    } catch {
      return;
    }
    if (!dataUrl.startsWith('data:image/')) {
      return;
    }

    const image = document.createElement('img');
    image.alt = canvas.getAttribute('aria-label') || '';
    image.src = dataUrl;
    image.width = canvas.width;
    image.height = canvas.height;
    image.style.cssText = canvas.style.cssText;
    if (!image.style.width) {
      image.style.width = `${canvas.clientWidth || canvas.width}px`;
    }
    if (!image.style.height) {
      image.style.height = `${canvas.clientHeight || canvas.height}px`;
    }
    image.dataset.printSnapshot = 'true';
    canvas.dataset.printSnapshot = 'replaced';
    canvas.replaceWith(image);
    images.push(image);
  });

  await Promise.all(images.map(waitForImageDecode));
};

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

async function preparePrintLayoutExpand(
  root: HTMLElement,
  options: { expandGridStack: boolean },
): Promise<void> {
  window.dispatchEvent(
    new CustomEvent(DASHBOARD_PREPARE_PRINT_EVENT, {
      detail: { phase: 'prepare-print' },
    }),
  );
  await waitForNextPaint();
  await snapshotCanvasesForPrint(root);

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

  if (options.expandGridStack) {
    root
      .querySelectorAll<HTMLElement>('.grid-stack')
      .forEach(applyExpandStyles);
  }

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

function resolveDashboardRenderRoot(
  root: HTMLElement | null,
): HTMLElement | null {
  if (root) {
    return root;
  }
  if (typeof document === 'undefined') {
    return null;
  }
  return document.querySelector<HTMLElement>('[data-dashboard-render-root="true"]');
}

/**
 * Expand the live render DOM so Chromium page.pdf() paginates full content.
 * Mirrors exportPdf expand rules without cloning or screenshot stitching.
 */
export async function prepareDashboardPrintLayout(
  root: HTMLElement | null = typeof document === 'undefined'
    ? null
    : document.querySelector<HTMLElement>('[data-dashboard-render-root="true"]'),
): Promise<void> {
  const resolvedRoot = resolveDashboardRenderRoot(root);
  if (!resolvedRoot) {
    throw new Error('Dashboard render root not found');
  }

  await preparePrintLayoutExpand(resolvedRoot, { expandGridStack: true });
}

/** Screen renderMode：保持视口尺寸，只把 WebGL canvas 冻成可印刷图片。 */
export async function prepareScreenPrintLayout(
  root: HTMLElement | null = typeof document === 'undefined'
    ? null
    : document.querySelector<HTMLElement>('[data-dashboard-render-root="true"]'),
): Promise<void> {
  const resolvedRoot = resolveDashboardRenderRoot(root);
  if (!resolvedRoot) {
    throw new Error('Screen render root not found');
  }

  window.dispatchEvent(
    new CustomEvent(DASHBOARD_PREPARE_PRINT_EVENT, {
      detail: { phase: 'prepare-print' },
    }),
  );
  await waitForNextPaint();
  await snapshotCanvasesForPrint(resolvedRoot);
  await waitForNextPaint();
}

/** Report renderMode：只展开 overflow，不查询 GridStack。 */
export async function prepareReportPrintLayout(
  root: HTMLElement | null = typeof document === 'undefined'
    ? null
    : document.querySelector<HTMLElement>('[data-dashboard-render-root="true"]'),
): Promise<void> {
  const resolvedRoot = resolveDashboardRenderRoot(root);
  if (!resolvedRoot) {
    throw new Error('Report render root not found');
  }

  await preparePrintLayoutExpand(resolvedRoot, { expandGridStack: false });
}
