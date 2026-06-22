export const LOG_GROUP_CREATE_SCOPE = 'log_group_create';

export const COMMON_LOG_GROUP_FIELDS = [
  '_stream',
  'host.name',
  'service.name',
  'container.name',
  'kubernetes.namespace',
  'log.file.path'
];

export type LogGroupFieldSource =
  | 'default'
  | 'expanded'
  | 'fallback'
  | 'permission-blocked';

interface FieldParams {
  scope?: string;
  start_time?: string;
  end_time?: string;
}

type GetFields = (params?: FieldParams) => Promise<string[]>;

const EXPANDED_LOOKBACK_MS = 24 * 60 * 60 * 1000;

const hasFields = (fields: string[]) => fields.length > 0;

const isPermissionError = (error: unknown) => {
  const maybeError = error as {
    response?: { status?: number };
    status?: number;
    message?: string;
  };
  const status = maybeError?.response?.status ?? maybeError?.status;
  const message = `${maybeError?.message || ''}`.toLowerCase();

  return status === 403 || message.includes('permission') || message.includes('权限');
};

export const discoverLogGroupRuleFields = async (
  getFields: GetFields,
  now = new Date()
): Promise<{ fields: string[]; source: LogGroupFieldSource }> => {
  try {
    const fields = await getFields({ scope: LOG_GROUP_CREATE_SCOPE });
    if (hasFields(fields)) {
      return { fields, source: 'default' };
    }
  } catch (error) {
    if (isPermissionError(error)) {
      return { fields: COMMON_LOG_GROUP_FIELDS, source: 'permission-blocked' };
    }
  }

  const endTime = now.toISOString();
  const startTime = new Date(now.getTime() - EXPANDED_LOOKBACK_MS).toISOString();

  try {
    const fields = await getFields({
      scope: LOG_GROUP_CREATE_SCOPE,
      start_time: startTime,
      end_time: endTime
    });
    if (hasFields(fields)) {
      return { fields, source: 'expanded' };
    }
  } catch (error) {
    if (isPermissionError(error)) {
      return { fields: COMMON_LOG_GROUP_FIELDS, source: 'permission-blocked' };
    }
  }

  return { fields: COMMON_LOG_GROUP_FIELDS, source: 'fallback' };
};
