export type TemplateSaveSection = 'basic' | 'metric' | 'alert' | 'notice';

export interface TemplateSaveFieldError {
  name: (string | number)[];
  errors: string[];
}

export interface TemplateSaveIssue {
  id: string;
  section: TemplateSaveSection;
  field: string;
  message: string;
}

const FIELD_SECTION: Record<string, TemplateSaveSection> = {
  name: 'basic',
  alert_name: 'basic',
  organizations: 'basic',
  source: 'basic',
  schedule: 'basic',
  collect_type: 'metric',
  metric: 'metric',
  query: 'metric',
  period: 'metric',
  algorithm: 'metric',
  threshold: 'alert',
  trigger_count: 'alert',
  recovery_condition: 'alert',
  no_data_alert_name: 'alert',
  notice: 'notice',
  notice_type_ids: 'notice',
  notice_users: 'notice',
  handlers: 'notice',
};

const FIELD_ORDER = Object.keys(FIELD_SECTION);

const splitMessages = (errors: string[]) =>
  errors.flatMap((error) =>
    String(error || '')
      .split('；')
      .map((item) => item.trim())
      .filter(Boolean)
  );

export const collectTemplateSaveIssues = (
  errorFields: TemplateSaveFieldError[] | null | undefined
): TemplateSaveIssue[] => {
  const issues: TemplateSaveIssue[] = [];
  const seen = new Set<string>();

  (errorFields || []).forEach((fieldError) => {
    const field = String(fieldError?.name?.[0] ?? '');
    if (!field) return;
    splitMessages(fieldError.errors || []).forEach((message) => {
      const id = `${field}:${message}`;
      if (seen.has(id)) return;
      seen.add(id);
      issues.push({
        id,
        section: FIELD_SECTION[field] || 'basic',
        field,
        message,
      });
    });
  });

  return issues.sort((left, right) => {
    const leftIndex = FIELD_ORDER.indexOf(left.field);
    const rightIndex = FIELD_ORDER.indexOf(right.field);
    return (leftIndex < 0 ? FIELD_ORDER.length : leftIndex) -
      (rightIndex < 0 ? FIELD_ORDER.length : rightIndex);
  });
};
