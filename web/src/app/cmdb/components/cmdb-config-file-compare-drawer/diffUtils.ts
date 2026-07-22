'use client';

type DiffStatus = 'unchanged' | 'added' | 'removed' | 'changed';

interface DiffRow {
  key: string;
  leftNumber: number | null;
  rightNumber: number | null;
  leftText: string;
  rightText: string;
  status: DiffStatus;
}

const splitLines = (content: string) => content.replace(/\r\n/g, '\n').split('\n');

export const buildSideBySideDiffRows = (
  leftContent: string,
  rightContent: string,
): DiffRow[] => {
  const leftLines = splitLines(leftContent);
  const rightLines = splitLines(rightContent);
  const maxLength = Math.max(leftLines.length, rightLines.length);

  return Array.from({ length: maxLength }, (_, index) => {
    const leftText = leftLines[index] ?? '';
    const rightText = rightLines[index] ?? '';
    const leftExists = index < leftLines.length;
    const rightExists = index < rightLines.length;

    let status: DiffStatus = 'unchanged';
    if (!leftExists && rightExists) {
      status = 'added';
    } else if (leftExists && !rightExists) {
      status = 'removed';
    } else if (leftText !== rightText) {
      status = 'changed';
    }

    return {
      key: `${index}-${status}`,
      leftNumber: leftExists ? index + 1 : null,
      rightNumber: rightExists ? index + 1 : null,
      leftText,
      rightText,
      status,
    };
  });
};

const buildLcsMatrix = (leftChars: string[], rightChars: string[]) => {
  const rows = leftChars.length + 1;
  const cols = rightChars.length + 1;
  const matrix = Array.from({ length: rows }, () => Array(cols).fill(0));

  for (let row = 1; row < rows; row += 1) {
    for (let col = 1; col < cols; col += 1) {
      if (leftChars[row - 1] === rightChars[col - 1]) {
        matrix[row][col] = matrix[row - 1][col - 1] + 1;
      } else {
        matrix[row][col] = Math.max(matrix[row - 1][col], matrix[row][col - 1]);
      }
    }
  }

  return matrix;
};

const collectDiffIndexes = (leftText: string, rightText: string) => {
  const leftChars = Array.from(leftText);
  const rightChars = Array.from(rightText);
  const matrix = buildLcsMatrix(leftChars, rightChars);
  const leftChanged = new Set<number>();
  const rightChanged = new Set<number>();

  let row = leftChars.length;
  let col = rightChars.length;

  while (row > 0 && col > 0) {
    if (leftChars[row - 1] === rightChars[col - 1]) {
      row -= 1;
      col -= 1;
      continue;
    }

    if (matrix[row - 1][col] >= matrix[row][col - 1]) {
      leftChanged.add(row - 1);
      row -= 1;
    } else {
      rightChanged.add(col - 1);
      col -= 1;
    }
  }

  while (row > 0) {
    leftChanged.add(row - 1);
    row -= 1;
  }

  while (col > 0) {
    rightChanged.add(col - 1);
    col -= 1;
  }

  return { leftChanged, rightChanged };
};

const buildSegments = (text: string, changedIndexes: Set<number>) => {
  if (!text.length) {
    return [{ text: '', changed: false }];
  }

  const chars = Array.from(text);
  const segments: Array<{ text: string; changed: boolean }> = [];
  let start = 0;
  let currentChanged = changedIndexes.has(0);

  for (let index = 1; index < chars.length; index += 1) {
    const isChanged = changedIndexes.has(index);
    if (isChanged === currentChanged) continue;

    segments.push({
      text: chars.slice(start, index).join(''),
      changed: currentChanged,
    });
    start = index;
    currentChanged = isChanged;
  }

  segments.push({
    text: chars.slice(start).join(''),
    changed: currentChanged,
  });

  return segments;
};

export const buildInlineSegments = (leftText: string, rightText: string) => {
  const { leftChanged, rightChanged } = collectDiffIndexes(leftText, rightText);

  return {
    left: buildSegments(leftText, leftChanged),
    right: buildSegments(rightText, rightChanged),
  };
};

export const getDiffAccentClassName = (
  status: DiffStatus,
  side: 'left' | 'right',
) => {
  if (status === 'changed') {
    return 'bg-amber-400/10';
  }

  if (status === 'added' && side === 'right') {
    return 'bg-emerald-400/10';
  }

  if (status === 'removed' && side === 'left') {
    return 'bg-rose-400/10';
  }

  return '';
};
