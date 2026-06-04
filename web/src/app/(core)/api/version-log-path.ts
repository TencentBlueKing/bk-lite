import fs from 'fs';
import path from 'path';

const SUPPORTED_LOCALES = new Set(['zh', 'en']);
const SAFE_SEGMENT_PATTERN = /^[A-Za-z0-9-]+$/;
const SAFE_FILE_PATTERN = /^[A-Za-z0-9._-]+\.md$/;

function isSafeSegment(value: string) {
  return SAFE_SEGMENT_PATTERN.test(value);
}

function isSafeLocale(value: string) {
  return SUPPORTED_LOCALES.has(value);
}

function getLegacyVersionsDirectory(clientId: string, locale: string) {
  return path.join(process.cwd(), 'public', 'app', 'versions', clientId, locale);
}

function getModuleVersionsDirectory(clientId: string, locale: string) {
  return path.join(process.cwd(), 'src', 'app', clientId, 'public', 'versions', clientId, locale);
}

export function resolveVersionsDirectory(clientId: string, locale: string) {
  if (!isSafeSegment(clientId) || !isSafeLocale(locale)) {
    return null;
  }

  const candidates = [
    getModuleVersionsDirectory(clientId, locale),
    getLegacyVersionsDirectory(clientId, locale),
  ];

  return candidates.find(candidate => fs.existsSync(candidate)) ?? candidates[0];
}

export function resolveVersionMarkdownPath(filePath: string) {
  const posixPath = filePath.replace(/\\/g, '/');
  const normalizedPath = path.posix.normalize(posixPath);

  if (
    normalizedPath !== posixPath ||
    path.posix.isAbsolute(normalizedPath) ||
    normalizedPath.startsWith('../') ||
    normalizedPath.includes('/../')
  ) {
    return null;
  }

  const parts = normalizedPath.split('/');
  if (parts.length !== 4 || parts[0] !== 'versions') {
    return null;
  }

  const [, clientId, locale, fileName] = parts;
  if (!isSafeSegment(clientId) || !isSafeLocale(locale) || !SAFE_FILE_PATTERN.test(fileName)) {
    return null;
  }

  const candidates = [
    path.join(getModuleVersionsDirectory(clientId, locale), fileName),
    path.join(getLegacyVersionsDirectory(clientId, locale), fileName),
  ];

  return candidates.find(candidate => fs.existsSync(candidate)) ?? candidates[0];
}
