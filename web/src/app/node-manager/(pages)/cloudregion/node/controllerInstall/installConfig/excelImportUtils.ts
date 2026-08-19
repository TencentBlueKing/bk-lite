import type { Group } from '@/types';

export type OrganizationId = string | number;

export interface OrganizationOption {
  label: string;
  name: string;
  value: OrganizationId;
}

export interface ExcelImportColumn {
  excel_label?: string;
  label: string;
  name?: string;
  type: string;
  widget_props?: {
    options?: Array<{ label: string; value?: unknown }>;
  };
}

export const findExcelImportColumn = <T extends ExcelImportColumn>(
  header: string,
  columns: T[]
) => {
  const cleanHeader = header.replace(/\s*\([^)]*\)\s*$/, '').trim();
  return columns.find(
    (column) =>
      column.excel_label === cleanHeader || column.label === cleanHeader
  );
};

export interface OptionSheetDefinition {
  columnIndex: number;
  options: string[];
  sheetName: string;
  state: 'visible' | 'hidden';
}

export interface OrganizationResolutionIssue {
  reason: 'unknown' | 'ambiguous';
  value: string;
}

export interface OrganizationCellResolution {
  ids: OrganizationId[] | null;
  issues: OrganizationResolutionIssue[];
}

const normalizeOrganizationId = (id: string): OrganizationId => {
  const numericId = Number(id);
  return Number.isNaN(numericId) ? id : numericId;
};

export const buildOrganizationOptions = (
  groups: Group[],
  parentPath = ''
): OrganizationOption[] =>
  groups.flatMap((group) => {
    const label = parentPath ? `${parentPath}/${group.name}` : group.name;
    const current = {
      label,
      name: group.name,
      value: normalizeOrganizationId(group.id)
    };
    const children = group.subGroups || group.children || [];

    return [current, ...buildOrganizationOptions(children, label)];
  });

const sanitizeSheetName = (name: string) =>
  name
    .replace(/[\\/*?:[\]]/g, '_')
    .replace(/^'+|'+$/g, '')
    .trim()
    .slice(0, 31);

const uniqueSheetName = (baseName: string, usedNames: Set<string>) => {
  const safeBaseName = sanitizeSheetName(baseName) || 'Options';
  let candidate = safeBaseName;
  let counter = 2;

  while (usedNames.has(candidate.toLowerCase())) {
    const suffix = `_${counter}`;
    candidate = `${safeBaseName.slice(0, 31 - suffix.length)}${suffix}`;
    counter += 1;
  }
  usedNames.add(candidate.toLowerCase());
  return candidate;
};

export const buildOptionSheetDefinitions = (
  columns: ExcelImportColumn[],
  organizationOptions: OrganizationOption[],
  optionsSuffix: string,
  reservedSheetNames: string[] = []
): OptionSheetDefinition[] => {
  const usedNames = new Set(
    reservedSheetNames.map((name) => name.toLowerCase())
  );

  return columns.flatMap((column, columnIndex) => {
    const options =
      column.type === 'group_select'
        ? organizationOptions.map((option) => option.label)
        : column.type === 'select'
          ? (column.widget_props?.options || []).map((option) => option.label)
          : [];

    if (options.length === 0) return [];

    return [
      {
        columnIndex,
        options,
        sheetName: uniqueSheetName(
          `${column.label}_${optionsSuffix}`,
          usedNames
        ),
        state: column.type === 'group_select' ? 'visible' : 'hidden'
      }
    ];
  });
};

const normalizeOrganizationPath = (value: string) =>
  value
    .split('/')
    .map((part) => part.trim())
    .join('/');

export const resolveOrganizationCell = (
  value: unknown,
  organizationOptions: OrganizationOption[]
): OrganizationCellResolution => {
  if (value === null || value === undefined || value === '') {
    return { ids: null, issues: [] };
  }

  const tokens = String(
    typeof value === 'object' && 'text' in value
      ? (value as { text: unknown }).text
      : value
  )
    .split(',')
    .map((token) => token.trim())
    .filter(Boolean);
  const ids: OrganizationId[] = [];
  const issues: OrganizationResolutionIssue[] = [];

  tokens.forEach((token) => {
    const idMatches = organizationOptions.filter(
      (option) => String(option.value) === token
    );
    if (idMatches.length === 1) {
      ids.push(idMatches[0].value);
      return;
    }
    const normalizedToken = normalizeOrganizationPath(token);
    const pathMatches = organizationOptions.filter(
      (option) => normalizeOrganizationPath(option.label) === normalizedToken
    );

    if (pathMatches.length === 1) {
      ids.push(pathMatches[0].value);
      return;
    }
    const leafMatches = organizationOptions.filter(
      (option) => option.name.trim() === token
    );
    if (leafMatches.length === 1) {
      ids.push(leafMatches[0].value);
      return;
    }
    issues.push({
      reason:
        idMatches.length > 1 || pathMatches.length > 1 || leafMatches.length > 1
          ? 'ambiguous'
          : 'unknown',
      value: token
    });
  });

  return { ids, issues };
};
