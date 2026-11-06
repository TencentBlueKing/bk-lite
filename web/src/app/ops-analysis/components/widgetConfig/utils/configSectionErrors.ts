export const CONFIG_SECTION_PRIORITY = ['data', 'singleStyle', 'interaction'] as const;

export type ConfigSection = (typeof CONFIG_SECTION_PRIORITY)[number];

export type ConfigFieldName = ReadonlyArray<string | number>;

/** 始终露在页签上方的字段。校验失败不切页。 */
const ALWAYS_VISIBLE_FIELDS = new Set([
  'name',
  'description',
  'dataSource',
  'chartType',
]);

export interface SectionErrorFlags {
  data: boolean;
  singleStyle: boolean;
  interaction: boolean;
}

export const emptySectionErrorFlags = (): SectionErrorFlags => ({
  data: false,
  singleStyle: false,
  interaction: false,
});

/**
 * 按字段名第一段归到配置分区。
 * `visible` 是页签外的常驻字段；`null` 表示这条错误没有名字，无法归类。
 * 其余未知字段归到数据页。
 */
export function sectionForConfigField(
  name: ConfigFieldName | string | number | null | undefined,
): ConfigSection | 'visible' | null {
  const path: ConfigFieldName | undefined = Array.isArray(name)
    ? name
    : (typeof name === 'string' || typeof name === 'number' ? [name] : undefined);
  if (!path || path.length === 0) return null;
  const head = path[0];
  if (head === 'interaction' || head === 'singleStyle') return head;
  if (typeof head === 'string' && ALWAYS_VISIBLE_FIELDS.has(head)) return 'visible';
  return 'data';
}

export function availableConfigSections(options: {
  variant: 'drawer' | 'panel';
  showSingleStyle: boolean;
}): ConfigSection[] {
  if (options.variant === 'panel' || !options.showSingleStyle) {
    return ['data', 'interaction'];
  }
  return ['data', 'singleStyle', 'interaction'];
}

/** 当前页已经有错误就留在当前页，否则按数据、样式、交互取第一个当前没显示的错误页。 */
export function pickConfigErrorSection(options: {
  current: ConfigSection;
  errored: readonly ConfigSection[];
  available?: readonly ConfigSection[];
}): ConfigSection | null {
  const available = new Set(options.available ?? CONFIG_SECTION_PRIORITY);
  const errored = options.errored.filter((section) => available.has(section));
  if (errored.length === 0) return null;
  if (available.has(options.current) && errored.includes(options.current)) {
    return options.current;
  }
  return CONFIG_SECTION_PRIORITY.find(
    (section) => section !== options.current && errored.includes(section),
  ) ?? null;
}

export interface ConfigFieldError {
  name: ConfigFieldName;
  section: ConfigSection | 'visible';
}

export function readConfigFieldErrors(error: unknown): ConfigFieldError[] | null {
  if (!error || typeof error !== 'object' || !('errorFields' in error)) return null;
  const fields = (error as { errorFields?: unknown }).errorFields;
  if (!Array.isArray(fields)) return null;
  const mapped: ConfigFieldError[] = [];
  for (const field of fields) {
    if (!field || typeof field !== 'object' || !('name' in field)) continue;
    const rawName = (field as { name?: unknown }).name;
    const name = Array.isArray(rawName)
      ? rawName as ConfigFieldName
      : (typeof rawName === 'string' || typeof rawName === 'number' ? [rawName] : undefined);
    const section = sectionForConfigField(name);
    if (!section || !name) continue;
    mapped.push({ name, section });
  }
  return mapped;
}

export function sectionErrorFlagsFromNames(
  fields: ReadonlyArray<{
    name?: ConfigFieldName | string | number | null;
    errors?: readonly string[];
  }>,
): SectionErrorFlags {
  const flags = emptySectionErrorFlags();
  fields.forEach((field) => {
    if (!field.errors?.length) return;
    const section = sectionForConfigField(field.name);
    if (section && section !== 'visible') flags[section] = true;
  });
  return flags;
}

export interface ValidationFailurePlan {
  fallback: boolean;
  /** 要显示的分区。null 表示不切页。 */
  section: ConfigSection | null;
  namePath?: ConfigFieldName;
  errors: SectionErrorFlags;
}

export function planValidationFailure(options: {
  error: unknown;
  current: ConfigSection;
  available: readonly ConfigSection[];
}): ValidationFailurePlan {
  const fields = readConfigFieldErrors(options.error);
  if (!fields || fields.length === 0) {
    return {
      fallback: true,
      section: null,
      errors: emptySectionErrorFlags(),
    };
  }
  const errored = fields
    .map((field) => field.section)
    .filter((section): section is ConfigSection => section !== 'visible');
  const target = pickConfigErrorSection({
    current: options.current,
    errored,
    available: options.available,
  });
  if (target) {
    return {
      fallback: false,
      section: target,
      namePath: fields.find((field) => field.section === target)?.name,
      errors: sectionErrorFlagsFromNames(
        fields.map((field) => ({ name: field.name, errors: ['invalid'] })),
      ),
    };
  }
  const visible = fields.find((field) => field.section === 'visible');
  if (visible) {
    return {
      fallback: false,
      section: null,
      namePath: visible.name,
      errors: emptySectionErrorFlags(),
    };
  }
  return {
    fallback: true,
    section: null,
    errors: emptySectionErrorFlags(),
  };
}
