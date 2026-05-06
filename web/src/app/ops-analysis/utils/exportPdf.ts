import { toCanvas } from 'html-to-image';
import jsPDF from 'jspdf';

const waitForNextPaint = () =>
  new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });

const syncFormState = (sourceRoot: HTMLElement, targetRoot: HTMLElement) => {
  const sourceFields = Array.from(
    sourceRoot.querySelectorAll('input, textarea, select')
  ) as Array<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>;
  const targetFields = Array.from(
    targetRoot.querySelectorAll('input, textarea, select')
  ) as Array<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>;

  sourceFields.forEach((sourceField, index) => {
    const targetField = targetFields[index];
    if (!targetField) return;

    if (sourceField instanceof HTMLInputElement && targetField instanceof HTMLInputElement) {
      if (sourceField.type === 'checkbox' || sourceField.type === 'radio') {
        targetField.checked = sourceField.checked;
      } else {
        targetField.value = sourceField.value;
      }
      return;
    }

    if (sourceField instanceof HTMLTextAreaElement && targetField instanceof HTMLTextAreaElement) {
      targetField.value = sourceField.value;
      return;
    }

    if (sourceField instanceof HTMLSelectElement && targetField instanceof HTMLSelectElement) {
      targetField.value = sourceField.value;
      targetField.selectedIndex = sourceField.selectedIndex;
    }
  });
};

const copyCanvasContent = (sourceRoot: HTMLElement, targetRoot: HTMLElement) => {
  const sourceCanvases = Array.from(sourceRoot.querySelectorAll('canvas')) as HTMLCanvasElement[];
  const targetCanvases = Array.from(targetRoot.querySelectorAll('canvas')) as HTMLCanvasElement[];

  sourceCanvases.forEach((sourceCanvas, index) => {
    const targetCanvas = targetCanvases[index];
    if (!targetCanvas) return;

    targetCanvas.width = sourceCanvas.width;
    targetCanvas.height = sourceCanvas.height;

    if (sourceCanvas.style.width) {
      targetCanvas.style.width = sourceCanvas.style.width;
    }
    if (sourceCanvas.style.height) {
      targetCanvas.style.height = sourceCanvas.style.height;
    }

    const context = targetCanvas.getContext('2d');
    if (!context) return;

    context.drawImage(sourceCanvas, 0, 0);
  });
};

const prepareCloneForExport = (cloneRoot: HTMLElement) => {
  cloneRoot.style.overflow = 'visible';
  cloneRoot.style.height = 'auto';
  cloneRoot.style.maxHeight = 'none';
  cloneRoot.style.minHeight = 'fit-content';
  cloneRoot.style.flex = 'none';

  const expandElements = Array.from(
    cloneRoot.querySelectorAll('[data-export-expand="true"]')
  ) as HTMLElement[];
  const hiddenElements = Array.from(
    cloneRoot.querySelectorAll('[data-export-hidden="true"]')
  ) as HTMLElement[];

  expandElements.forEach((expandElement) => {
    expandElement.style.overflow = 'visible';
    expandElement.style.height = 'auto';
    expandElement.style.maxHeight = 'none';
    expandElement.style.minHeight = 'fit-content';
    expandElement.style.flex = 'none';
  });

  hiddenElements.forEach((hiddenElement) => {
    hiddenElement.style.display = 'none';
  });
};

const createExportClone = async (element: HTMLElement) => {
  const container = document.createElement('div');
  const clone = element.cloneNode(true) as HTMLElement;
  const width = Math.ceil(element.getBoundingClientRect().width);

  container.style.position = 'fixed';
  container.style.left = '-100000px';
  container.style.top = '0';
  container.style.zIndex = '-1';
  container.style.pointerEvents = 'none';
  container.style.background = '#f5f5f5';
  container.style.padding = '0';
  container.style.margin = '0';

  clone.style.width = `${width}px`;
  clone.style.margin = '0';

  container.appendChild(clone);
  document.body.appendChild(container);

  syncFormState(element, clone);
  prepareCloneForExport(clone);
  copyCanvasContent(element, clone);

  await waitForNextPaint();

  return { container, clone };
};

export async function exportDashboardToPdf(
  element: HTMLElement,
  filename: string = 'dashboard'
) {
  const { container, clone } = await createExportClone(element);

  try {
    const canvas = await toCanvas(clone, {
      pixelRatio: 2,
      backgroundColor: '#f5f5f5',
    });

    const pdfWidth = 297;
    const pdfHeight = 210;
    const margin = 10;
    const contentWidth = pdfWidth - margin * 2;
    const contentHeight = pdfHeight - margin * 2;
    const imgHeight = (canvas.height * contentWidth) / canvas.width;

    const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });

    if (imgHeight <= contentHeight) {
      pdf.addImage(canvas.toDataURL('image/png'), 'PNG', margin, margin, contentWidth, imgHeight);
    } else {
      let pageIndex = 0;
      let srcY = 0;
      const totalSrcHeight = canvas.height;
      const srcPageHeight = (contentHeight / imgHeight) * totalSrcHeight;

      while (srcY < totalSrcHeight) {
        if (pageIndex > 0) pdf.addPage();
        const currentSrcHeight = Math.min(srcPageHeight, totalSrcHeight - srcY);
        const currentDestHeight = (currentSrcHeight / totalSrcHeight) * imgHeight;

        const pageCanvas = document.createElement('canvas');
        pageCanvas.width = canvas.width;
        pageCanvas.height = currentSrcHeight;
        const context = pageCanvas.getContext('2d');
        if (context) {
          context.drawImage(canvas, 0, srcY, canvas.width, currentSrcHeight, 0, 0, canvas.width, currentSrcHeight);
          pdf.addImage(pageCanvas.toDataURL('image/png'), 'PNG', margin, margin, contentWidth, currentDestHeight);
        }

        srcY += srcPageHeight;
        pageIndex++;
      }
    }

    pdf.save(`${filename}.pdf`);
  } finally {
    container.remove();
  }
}
