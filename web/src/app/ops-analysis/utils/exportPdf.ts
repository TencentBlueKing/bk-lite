import { toCanvas } from 'html-to-image';
import jsPDF from 'jspdf';

export async function exportDashboardToPdf(
  element: HTMLElement,
  filename: string = 'dashboard'
) {
  const scrollContainer = element.querySelector('.overflow-auto') as HTMLElement | null;
  const expandElements = Array.from(
    element.querySelectorAll('[data-export-expand="true"]')
  ) as HTMLElement[];
  const hiddenElements = Array.from(
    element.querySelectorAll('[data-export-hidden="true"]')
  ) as HTMLElement[];
  const savedStyles: Record<string, string> = {};
  const savedExpandStyles = expandElements.map((expandElement) => ({
    element: expandElement,
    overflow: expandElement.style.overflow,
    height: expandElement.style.height,
    maxHeight: expandElement.style.maxHeight,
    minHeight: expandElement.style.minHeight,
    flex: expandElement.style.flex,
  }));
  const savedHiddenDisplays = hiddenElements.map((hiddenElement) => ({
    element: hiddenElement,
    display: hiddenElement.style.display,
  }));

  if (scrollContainer) {
    savedStyles.overflow = scrollContainer.style.overflow;
    savedStyles.height = scrollContainer.style.height;
    savedStyles.maxHeight = scrollContainer.style.maxHeight;
    scrollContainer.style.overflow = 'visible';
    scrollContainer.style.height = 'auto';
    scrollContainer.style.maxHeight = 'none';
  }

  savedStyles.parentOverflow = element.style.overflow;
  savedStyles.parentHeight = element.style.height;
  savedStyles.parentMaxHeight = element.style.maxHeight;
  savedStyles.parentMinHeight = element.style.minHeight;
  savedStyles.parentFlex = element.style.flex;
  element.style.overflow = 'visible';
  element.style.height = 'auto';
  element.style.maxHeight = 'none';
  element.style.minHeight = 'fit-content';
  element.style.flex = 'none';

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

  try {
    const canvas = await toCanvas(element, {
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
        const ctx = pageCanvas.getContext('2d');
        if (ctx) {
          ctx.drawImage(canvas, 0, srcY, canvas.width, currentSrcHeight, 0, 0, canvas.width, currentSrcHeight);
          pdf.addImage(pageCanvas.toDataURL('image/png'), 'PNG', margin, margin, contentWidth, currentDestHeight);
        }

        srcY += srcPageHeight;
        pageIndex++;
      }
    }

    pdf.save(`${filename}.pdf`);
  } finally {
    savedExpandStyles.forEach(({ element: expandElement, overflow, height, maxHeight, minHeight, flex }) => {
      expandElement.style.overflow = overflow;
      expandElement.style.height = height;
      expandElement.style.maxHeight = maxHeight;
      expandElement.style.minHeight = minHeight;
      expandElement.style.flex = flex;
    });

    savedHiddenDisplays.forEach(({ element: hiddenElement, display }) => {
      hiddenElement.style.display = display;
    });

    if (scrollContainer) {
      scrollContainer.style.overflow = savedStyles.overflow;
      scrollContainer.style.height = savedStyles.height;
      scrollContainer.style.maxHeight = savedStyles.maxHeight;
    }
    element.style.overflow = savedStyles.parentOverflow;
    element.style.height = savedStyles.parentHeight;
    element.style.maxHeight = savedStyles.parentMaxHeight;
    element.style.minHeight = savedStyles.parentMinHeight;
    element.style.flex = savedStyles.parentFlex;

    requestAnimationFrame(() => {
      window.dispatchEvent(new CustomEvent('ops-analysis:dashboard-export-restored'));
    });
  }
}
