type ScrollValue = number | string;

export interface CustomTableScroll {
  x?: ScrollValue | true;
  y?: ScrollValue;
  scrollToFirstRowOnChange?: boolean;
}

interface ResolveTableScrollOptions {
  calculatedScrollX: number | undefined;
  scroll: CustomTableScroll | undefined;
  calculatedScrollY: number | undefined;
  hasData: boolean;
}

export const resolveTableScroll = ({
  calculatedScrollX,
  scroll,
  calculatedScrollY,
  hasData,
}: ResolveTableScrollOptions): CustomTableScroll => {
  const resolvedScroll: CustomTableScroll = {
    ...(calculatedScrollX !== undefined && hasData
      ? { x: calculatedScrollX }
      : {}),
    ...scroll,
  };
  const hasExplicitScrollY = scroll?.y !== undefined && scroll?.y !== null;

  if (
    calculatedScrollY !== undefined &&
    (hasData || hasExplicitScrollY)
  ) {
    resolvedScroll.y = calculatedScrollY;
  }

  if (!hasData && !hasExplicitScrollY) {
    delete resolvedScroll.y;
  }

  return resolvedScroll;
};
