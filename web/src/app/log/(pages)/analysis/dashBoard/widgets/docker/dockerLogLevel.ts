export type DockerLogLevel = 'ERROR' | 'WARN' | 'INFO' | 'DEBUG' | 'UNKNOWN';

export const DOCKER_LEVEL_ORDER: DockerLogLevel[] = [
  'ERROR',
  'WARN',
  'INFO',
  'DEBUG',
  'UNKNOWN'
];

export const DOCKER_LEVEL_COLORS: Record<DockerLogLevel, string> = {
  ERROR: '#f5222d',
  WARN: '#faad14',
  INFO: '#1677ff',
  DEBUG: '#8c8c8c',
  UNKNOWN: '#fa8c16'
};

export const normalizeDockerLevel = (message: string): DockerLogLevel => {
  if (!message) return 'UNKNOWN';

  if (/\b(FATAL|ERROR)\b/i.test(message) || /\bError\b/.test(message)) {
    return 'ERROR';
  }

  if (/\b(WARN|WARNING|DEPRECATION)\b/i.test(message)) {
    return 'WARN';
  }

  if (/\bDEBUG\b/i.test(message)) {
    return 'DEBUG';
  }

  if (
    /\bINFO\b/i.test(message) ||
    /\bI\s{2,}\w+\b/.test(message) ||
    /\bLOG:/i.test(message)
  ) {
    return 'INFO';
  }

  return 'UNKNOWN';
};
