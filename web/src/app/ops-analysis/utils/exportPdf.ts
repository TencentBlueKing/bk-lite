import { toCanvas } from 'html-to-image';
import jsPDF from 'jspdf';

export async function exportDashboardToPdf(
  element: HTMLElement,
  filename: string = 'dashboard'
) {
  const scrollContainer = element.querySelector('.overflow-auto') as HTMLElement | null;
  const hiddenElements = Array.from(
    element.querySelectorAll('[data-export-hidden="true"]')
  ) as HTMLElement[];
  const savedStyles: Record<string, string> = {};
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
  element.style.overflow = 'visible';

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
    savedHiddenDisplays.forEach(({ element: hiddenElement, display }) => {
      hiddenElement.style.display = display;
    });

    if (scrollContainer) {
      scrollContainer.style.overflow = savedStyles.overflow;
      scrollContainer.style.height = savedStyles.height;
      scrollContainer.style.maxHeight = savedStyles.maxHeight;
    }
    element.style.overflow = savedStyles.parentOverflow;
  }
}
