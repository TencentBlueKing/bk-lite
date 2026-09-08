export interface CanvasBox {
  width: number;
  height: number;
}

export function readStableCanvasBox(element: HTMLElement): CanvasBox | null {
  const width = Math.round(element.clientWidth);
  const height = Math.round(element.clientHeight);
  if (width < 8 || height < 8) {
    return null;
  }
  return { width, height };
}

export function canvasBoxChanged(
  previous: CanvasBox | null,
  next: CanvasBox,
): boolean {
  return (
    !previous || previous.width !== next.width || previous.height !== next.height
  );
}
