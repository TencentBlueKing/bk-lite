export interface OrganizationRecord {
  team_name?: string[] | null;
}

const CELL_HORIZONTAL_PADDING = 32;
const TAG_HORIZONTAL_PADDING_AND_BORDER = 16;
const TAG_GAP = 4;
const LATIN_CHARACTER_WIDTH = 8;
const WIDE_CHARACTER_WIDTH = 14;

const estimateTextWidth = (text: string) =>
  Array.from(text).reduce(
    (width, character) =>
      width + (/[^\u0000-\u00ff]/.test(character) ? WIDE_CHARACTER_WIDTH : LATIN_CHARACTER_WIDTH),
    0
  );

export const getOrganizationColumnWidth = <T extends OrganizationRecord>(
  records: T[],
  minWidth = 120
) => records.reduce((maxWidth, record) => {
  const names = record.team_name || [];
  if (names.length === 0) return maxWidth;

  const tagsWidth = names.reduce(
    (total, name) => total + estimateTextWidth(name) + TAG_HORIZONTAL_PADDING_AND_BORDER,
    0
  );
  const gapsWidth = Math.max(0, names.length - 1) * TAG_GAP;

  return Math.max(maxWidth, tagsWidth + gapsWidth + CELL_HORIZONTAL_PADDING);
}, minWidth);
