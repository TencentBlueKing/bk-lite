export interface SearchJumpQuery {
  query?: string;
  window_start?: number | string | null;
  window_end?: number | string | null;
}

export interface SearchJumpInput {
  jumpQuery?: SearchJumpQuery | null;
  fallbackQuery?: string;
  fallbackStart?: string | number;
  fallbackEnd?: string | number;
  logGroups?: Array<string | number>;
}

export function toSearchMillis(value: string | number): string {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return String(value);
  }
  return String(number < 1e10 ? number * 1000 : number);
}

export function buildSearchJumpUrl(input: SearchJumpInput): string {
  const jump = input.jumpQuery;
  const query = jump?.query || input.fallbackQuery || '';
  const start =
    jump?.window_start != null && jump.window_start !== ''
      ? toSearchMillis(jump.window_start)
      : input.fallbackStart;
  const end =
    jump?.window_end != null && jump.window_end !== ''
      ? toSearchMillis(jump.window_end)
      : input.fallbackEnd;
  const params = new URLSearchParams();
  if (query) {
    params.set('query', query);
  }
  if (start != null && start !== '') {
    params.set('startTime', String(start));
  }
  if (end != null && end !== '') {
    params.set('endTime', String(end));
  }
  for (const group of input.logGroups || []) {
    if (group === undefined || group === null || group === '') {
      continue;
    }
    params.append('log_groups', String(group));
  }
  const queryString = params.toString();
  return queryString ? `/log/search?${queryString}` : '/log/search';
}
