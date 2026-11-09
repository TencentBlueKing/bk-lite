export const MIN_TABLE_BODY_HEIGHT = 160;

type TableSize = 'small' | 'middle' | 'large';

interface ResolveTableDimensionsOptions {
  scrollY: number | string | undefined;
  viewportHeight: number;
  parentHeight: number;
  size: TableSize;
  hasPagination: boolean;
}

interface TableDimensions {
  tableHeight: number | undefined;
  containerHeight: number | undefined;
}

const TABLE_HEADER_HEIGHT: Record<TableSize, number> = {
  small: 47,
  middle: 55,
  large: 63,
};

const parseScrollY = (
  value: number | string,
  viewportHeight: number
): number | undefined => {
  if (typeof value === 'number') return value;

  let total = 0;
  let matched = false;
  const calcRegex = /([-+]?)\s*(\d*\.?\d+)(vh|px)/g;
  let match: RegExpExecArray | null;

  while ((match = calcRegex.exec(value)) !== null) {
    matched = true;
    const sign = match[1] || '+';
    const number = Number.parseFloat(match[2]);
    const result = match[3] === 'vh' ? (number / 100) * viewportHeight : number;
    total += sign === '-' ? -result : result;
  }

  return matched ? total : undefined;
};

export const resolveTableDimensions = ({
  scrollY,
  viewportHeight,
  parentHeight,
  size,
  hasPagination,
}: ResolveTableDimensionsOptions): TableDimensions => {
  const headerHeight = TABLE_HEADER_HEIGHT[size];
  const paginationHeight = hasPagination ? 56 : 0;
  const fixedHeight = headerHeight + paginationHeight;

  if (scrollY === 'auto') {
    return { tableHeight: undefined, containerHeight: undefined };
  }

  if (scrollY !== undefined && scrollY !== null) {
    const parsedHeight = parseScrollY(scrollY, viewportHeight);
    if (parsedHeight === undefined) {
      return { tableHeight: undefined, containerHeight: undefined };
    }

    // 数字是调用方按父容器量好的表体高度。再抬到 160 会让矮卡片里的
    // 滚动容器高出 overflow:hidden 的父级，滚动条落到可见区域外面。
    // vh/px 字符串仍保留下限，避免把历史的视口估算收成一条缝。
    const tableHeight = typeof scrollY === 'number'
      ? Math.max(0, parsedHeight)
      : Math.max(MIN_TABLE_BODY_HEIGHT, parsedHeight);
    return {
      tableHeight,
      containerHeight: tableHeight + fixedHeight,
    };
  }

  if (!hasPagination) {
    return { tableHeight: undefined, containerHeight: undefined };
  }

  if (parentHeight <= 0) {
    return { tableHeight: undefined, containerHeight: undefined };
  }

  return {
    tableHeight: Math.max(0, parentHeight - fixedHeight),
    containerHeight: parentHeight,
  };
};

export const createRafScheduler = (
  callback: () => void,
  requestFrame: (callback: FrameRequestCallback) => number,
  cancelFrame: (frameId: number) => void
) => {
  let frameId: number | undefined;

  const cancel = () => {
    if (frameId === undefined) return;
    cancelFrame(frameId);
    frameId = undefined;
  };

  const schedule = () => {
    cancel();
    frameId = requestFrame(() => {
      frameId = undefined;
      callback();
    });
  };

  return { schedule, cancel };
};
