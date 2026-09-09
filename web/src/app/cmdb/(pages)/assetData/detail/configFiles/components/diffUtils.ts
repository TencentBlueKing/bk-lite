export interface DiffRow {
  key: string;
  leftNumber: number | null;
  rightNumber: number | null;
  leftText: string;
  rightText: string;
  status: 'same' | 'changed' | 'added' | 'removed';
}

export interface DiffSegment {
  text: string;
  changed: boolean;
}

export interface AlignedDiffResult {
  kind: 'aligned';
  rows: DiffRow[];
}

export interface OverBudgetDiffResult {
  kind: 'over_budget';
  cellCount: number;
  maxCells: number;
}

export type SideBySideDiffResult = AlignedDiffResult | OverBudgetDiffResult;

// 页面入口真实文案：菜单「资产」→「配置文件」；页头「配置文件列表」；按钮「与上版本对比」；抽屉「版本对比」。
export const MAX_DIFF_LCS_CELLS = 1_000_000;

export const buildSideBySideDiffRows = (
  leftContent: string,
  rightContent: string
): SideBySideDiffResult => {
  const leftLines = leftContent.split(/\r?\n/);
  const rightLines = rightContent.split(/\r?\n/);
  const leftLength = leftLines.length;
  const rightLength = rightLines.length;
  const cellCount = (leftLength + 1) * (rightLength + 1);
  if (cellCount > MAX_DIFF_LCS_CELLS) {
    return {
      kind: 'over_budget',
      cellCount,
      maxCells: MAX_DIFF_LCS_CELLS,
    };
  }
  const dp = Array.from({ length: leftLength + 1 }, () => Array(rightLength + 1).fill(0));

  for (let leftIndex = leftLength - 1; leftIndex >= 0; leftIndex -= 1) {
    for (let rightIndex = rightLength - 1; rightIndex >= 0; rightIndex -= 1) {
      if (leftLines[leftIndex] === rightLines[rightIndex]) {
        dp[leftIndex][rightIndex] = dp[leftIndex + 1][rightIndex + 1] + 1;
      } else {
        dp[leftIndex][rightIndex] = Math.max(dp[leftIndex + 1][rightIndex], dp[leftIndex][rightIndex + 1]);
      }
    }
  }

  const rows: DiffRow[] = [];
  let leftIndex = 0;
  let rightIndex = 0;
  let leftNumber = 1;
  let rightNumber = 1;

  while (leftIndex < leftLength && rightIndex < rightLength) {
    if (leftLines[leftIndex] === rightLines[rightIndex]) {
      rows.push({
        key: `${leftIndex}-${rightIndex}`,
        leftNumber,
        rightNumber,
        leftText: leftLines[leftIndex],
        rightText: rightLines[rightIndex],
        status: 'same',
      });
      leftIndex += 1;
      rightIndex += 1;
      leftNumber += 1;
      rightNumber += 1;
      continue;
    }

    if (dp[leftIndex + 1][rightIndex] === dp[leftIndex][rightIndex + 1]) {
      rows.push({
        key: `${leftIndex}-${rightIndex}`,
        leftNumber,
        rightNumber,
        leftText: leftLines[leftIndex],
        rightText: rightLines[rightIndex],
        status: 'changed',
      });
      leftIndex += 1;
      rightIndex += 1;
      leftNumber += 1;
      rightNumber += 1;
      continue;
    }

    if (dp[leftIndex + 1][rightIndex] > dp[leftIndex][rightIndex + 1]) {
      rows.push({
        key: `${leftIndex}-left`,
        leftNumber,
        rightNumber: null,
        leftText: leftLines[leftIndex],
        rightText: '',
        status: 'removed',
      });
      leftIndex += 1;
      leftNumber += 1;
      continue;
    }

    rows.push({
      key: `${rightIndex}-right`,
      leftNumber: null,
      rightNumber,
      leftText: '',
      rightText: rightLines[rightIndex],
      status: 'added',
    });
    rightIndex += 1;
    rightNumber += 1;
  }

  while (leftIndex < leftLength) {
    rows.push({
      key: `${leftIndex}-left-tail`,
      leftNumber,
      rightNumber: null,
      leftText: leftLines[leftIndex],
      rightText: '',
      status: 'removed',
    });
    leftIndex += 1;
    leftNumber += 1;
  }

  while (rightIndex < rightLength) {
    rows.push({
      key: `${rightIndex}-right-tail`,
      leftNumber: null,
      rightNumber,
      leftText: '',
      rightText: rightLines[rightIndex],
      status: 'added',
    });
    rightIndex += 1;
    rightNumber += 1;
  }

  return { kind: 'aligned', rows };
};

export const getDiffAccentClassName = (status: DiffRow['status'], side: 'left' | 'right') => {
  if (status === 'changed') return 'border-l-2 border-l-amber-400';
  if (status === 'added' && side === 'right') return 'border-l-2 border-l-emerald-400';
  if (status === 'removed' && side === 'left') return 'border-l-2 border-l-rose-400';
  return 'border-l-2 border-l-transparent';
};

export const buildInlineSegments = (leftText: string, rightText: string) => {
  if (leftText === rightText) {
    return {
      left: [{ text: leftText, changed: false }],
      right: [{ text: rightText, changed: false }],
    };
  }

  let prefixLength = 0;
  const maxPrefixLength = Math.min(leftText.length, rightText.length);
  while (prefixLength < maxPrefixLength && leftText[prefixLength] === rightText[prefixLength]) {
    prefixLength += 1;
  }

  let leftSuffixLength = leftText.length - 1;
  let rightSuffixLength = rightText.length - 1;
  while (
    leftSuffixLength >= prefixLength &&
    rightSuffixLength >= prefixLength &&
    leftText[leftSuffixLength] === rightText[rightSuffixLength]
  ) {
    leftSuffixLength -= 1;
    rightSuffixLength -= 1;
  }

  const buildSegments = (source: string, suffixIndex: number): DiffSegment[] => {
    const segments: DiffSegment[] = [];
    const prefix = source.slice(0, prefixLength);
    const changed = source.slice(prefixLength, suffixIndex + 1);
    const suffix = source.slice(suffixIndex + 1);

    if (prefix) segments.push({ text: prefix, changed: false });
    if (changed) segments.push({ text: changed, changed: true });
    if (suffix) segments.push({ text: suffix, changed: false });
    if (!segments.length) segments.push({ text: '', changed: false });
    return segments;
  };

  return {
    left: buildSegments(leftText, leftSuffixLength),
    right: buildSegments(rightText, rightSuffixLength),
  };
};
