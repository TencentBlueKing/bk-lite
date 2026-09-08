export interface ExecutionParamItem {
  name?: string;
  value?: unknown;
}

export type ExecutionParams =
  | string
  | Record<string, unknown>
  | ExecutionParamItem[]
  | null
  | undefined;

const ACTIVE_EXECUTION_STATUSES = new Set(['pending', 'running', 'cancelling']);

export function isActiveExecutionStatus(status?: string | null): boolean {
  return !!status && ACTIVE_EXECUTION_STATUSES.has(status);
}

export function shouldPollExecutionList(
  records: Array<{ status?: string | null }>
): boolean {
  return records.some((record) => isActiveExecutionStatus(record.status));
}

export function parseCommandLineArgs(input: string): string[] {
  const args: string[] = [];
  let current = '';
  let quote: 'single' | 'double' | null = null;
  let tokenStarted = false;

  const pushCurrent = () => {
    if (!tokenStarted) return;
    args.push(current);
    current = '';
    tokenStarted = false;
  };

  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];

    if (quote === 'single') {
      if (char === "'") {
        quote = null;
      } else {
        current += char;
      }
      continue;
    }

    if (quote === 'double') {
      if (char === '"') {
        quote = null;
      } else if (char === '\\' && index + 1 < input.length) {
        index += 1;
        current += input[index];
      } else {
        current += char;
      }
      continue;
    }

    if (/\s/.test(char)) {
      pushCurrent();
    } else if (char === "'") {
      quote = 'single';
      tokenStarted = true;
    } else if (char === '"') {
      quote = 'double';
      tokenStarted = true;
    } else if (char === '\\' && index + 1 < input.length) {
      tokenStarted = true;
      index += 1;
      current += input[index];
    } else {
      tokenStarted = true;
      current += char;
    }
  }

  pushCurrent();
  return args;
}

function quoteCommandLineArg(value: unknown): string {
  const text = String(value ?? '');
  if (text === '') return "''";
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(text)) return text;
  return `'${text.replace(/'/g, `'"'"'`)}'`;
}

export function replayManualParamsText(params: ExecutionParams): string {
  if (typeof params === 'string') return params;
  if (Array.isArray(params)) {
    return params.map((item) => quoteCommandLineArg(item.value)).join(' ');
  }
  if (params && typeof params === 'object') {
    return Object.values(params).map(quoteCommandLineArg).join(' ');
  }
  return '';
}

function paramsToRecord(params: ExecutionParams): Record<string, unknown> {
  if (typeof params === 'string') {
    const trimmed = params.trim();
    if (!trimmed) return {};
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      return parsed && !Array.isArray(parsed) && typeof parsed === 'object'
        ? (parsed as Record<string, unknown>)
        : {};
    } catch {
      return {};
    }
  }

  if (Array.isArray(params)) {
    return params.reduce<Record<string, unknown>>((result, item) => {
      if (item.name) result[item.name] = item.value;
      return result;
    }, {});
  }

  return params && typeof params === 'object' ? params : {};
}

export function replayTemplateParamFields(
  params: ExecutionParams
): Record<string, unknown> {
  return Object.entries(paramsToRecord(params)).reduce<Record<string, unknown>>(
    (result, [name, value]) => {
      result[`param_${name}`] = value;
      return result;
    },
    {}
  );
}

export function hasExecutionParams(params: ExecutionParams): boolean {
  if (typeof params === 'string') return params.trim().length > 0;
  if (Array.isArray(params)) return params.length > 0;
  return !!params && typeof params === 'object' && Object.keys(params).length > 0;
}

export function formatExecutionParams(params: ExecutionParams): string {
  if (!hasExecutionParams(params)) return '';
  if (typeof params !== 'string') return JSON.stringify(params, null, 2);

  const trimmed = params.trim();
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch {
    return params;
  }
}
