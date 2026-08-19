/** JS 字号是 px，打印重排变窄时不会再跑。用 cqi 让 CSS 按容器宽度再收一次。 */
export function evaluatePrintSafeFontSize(
  fittedPx: number,
  textWidthPx: number,
  containerWidthPx: number,
): number {
  if (!(fittedPx > 0) || !(textWidthPx > 0) || !(containerWidthPx > 0)) {
    return Math.max(fittedPx, 0);
  }
  return Math.min(fittedPx, (containerWidthPx * fittedPx) / textWidthPx);
}

const formatCqiCap = (textWidthPx: number, fittedPx: number) =>
  String(Number(((100 * fittedPx) / textWidthPx).toFixed(4)));

export function buildPrintSafeFontSize(
  fittedPx: number,
  textWidthPx: number,
): string {
  if (!(fittedPx > 0)) {
    return '0px';
  }
  if (!(textWidthPx > 0)) {
    return `${fittedPx}px`;
  }
  return `min(${fittedPx}px, ${formatCqiCap(textWidthPx, fittedPx)}cqi)`;
}
