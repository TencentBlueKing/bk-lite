export const LINE_SINGLE_POINT_SYMBOL_SIZE = 8;

const isRenderablePoint = (value: unknown): boolean => {
  if (Array.isArray(value)) {
    return isRenderablePoint(value[value.length - 1]);
  }
  if (value === null || value === undefined || value === '') {
    return false;
  }
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric);
};

export const countRenderableLinePoints = (data: unknown): number => {
  if (!Array.isArray(data)) return 0;
  return data.filter(isRenderablePoint).length;
};

/** 两个及以上采样点画折线并隐藏拐点；只有一个点时折线不存在，改画圆点。 */
export const resolveLineSeriesPointMark = (pointCount: number) => {
  if (pointCount === 1) {
    return {
      showSymbol: true,
      showAllSymbol: true,
      symbol: 'circle' as const,
      symbolSize: LINE_SINGLE_POINT_SYMBOL_SIZE,
    };
  }
  return {
    showSymbol: false,
    showAllSymbol: false,
    symbol: 'none' as const,
    symbolSize: 0,
  };
};
