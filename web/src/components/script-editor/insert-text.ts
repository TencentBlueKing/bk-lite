export interface TextPoint {
  row: number;
  column: number;
}

export interface TextRange {
  start: TextPoint;
  end: TextPoint;
}

export interface TextInsertResult {
  value: string;
  cursor: TextPoint;
}

const splitLines = (content: string) => content.split('\n');

const pointAtEnd = (content: string): TextPoint => {
  const lines = splitLines(content);
  return { row: lines.length - 1, column: lines[lines.length - 1].length };
};

const pointAtOffset = (content: string, offset: number): TextPoint => {
  const lines = splitLines(content);
  let remaining = Math.max(offset, 0);
  for (let row = 0; row < lines.length; row += 1) {
    if (remaining <= lines[row].length) {
      return { row, column: remaining };
    }
    remaining -= lines[row].length + 1;
  }
  return pointAtEnd(content);
};

const toOffset = (content: string, point: TextPoint) => {
  const lines = splitLines(content);
  const row = Math.min(Math.max(point.row, 0), lines.length - 1);
  const column = Math.min(Math.max(point.column, 0), lines[row].length);
  let offset = column;
  for (let index = 0; index < row; index += 1) {
    offset += lines[index].length + 1;
  }
  return offset;
};

/** 在选区替换文本。没有选区时追加到末尾。 */
export const insertTextAtRange = (
  content: string,
  range: TextRange | null,
  text: string,
): TextInsertResult => {
  const source = content || '';
  if (!text) {
    return { value: source, cursor: range ? pointAtOffset(source, toOffset(source, range.end)) : pointAtEnd(source) };
  }
  if (!range) {
    const value = source + text;
    return { value, cursor: pointAtEnd(value) };
  }
  const start = toOffset(source, range.start);
  const end = toOffset(source, range.end);
  const from = Math.min(start, end);
  const to = Math.max(start, end);
  const value = source.slice(0, from) + text + source.slice(to);
  return { value, cursor: pointAtOffset(value, from + text.length) };
};
