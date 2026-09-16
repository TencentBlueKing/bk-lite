type ScrollValue = number | string;

export interface CustomTableScroll {
  x?: ScrollValue | true;
  y?: ScrollValue;
  scrollToFirstRowOnChange?: boolean;
}

interface ResolveTableScrollOptions {
  calculatedScrollX: number | undefined;
  containerWidth?: number;
  scroll: CustomTableScroll | undefined;
  calculatedScrollY: number | undefined;
  hasData: boolean;
}

const isFillableScrollX = (value: CustomTableScroll['x']): boolean =>
  value === undefined || value === 'max-content' || value === true;

export const resolveTableScroll = ({
  calculatedScrollX,
  containerWidth,
  scroll,
  calculatedScrollY,
  hasData,
}: ResolveTableScrollOptions): CustomTableScroll => {
  const resolvedScroll: CustomTableScroll = {
    ...scroll,
  };

  if (isFillableScrollX(scroll?.x)) {
    const overflowsContainer =
      typeof calculatedScrollX === 'number'
      && typeof containerWidth === 'number'
      && containerWidth > 0
      && calculatedScrollX > containerWidth;
    if (overflowsContainer) {
      resolvedScroll.x = calculatedScrollX;
    } else {
      delete resolvedScroll.x;
    }
  }

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
