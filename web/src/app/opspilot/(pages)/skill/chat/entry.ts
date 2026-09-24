const STORAGE_KEY = 'opspilot.webChatEntry';

type EntryMap = Record<string, string>;

const readMap = (): EntryMap => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const writeMap = (entries: EntryMap) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
};

/** 打开对话页前写入一次性凭证，地址栏不出现渠道 ID。 */
export const rememberWebChatEntry = (channelId: number): string => {
  const token = crypto.randomUUID();
  const entries = readMap();
  entries[token] = String(channelId);
  const tokens = Object.keys(entries);
  for (const stale of tokens.slice(0, Math.max(0, tokens.length - 10))) {
    delete entries[stale];
  }
  writeMap(entries);
  return token;
};

/** 读取凭证对应的渠道。凭证只存在于当前浏览器，改地址栏里的值对不上。 */
export const readWebChatEntry = (token: string): string => {
  if (!token) return '';
  const entries = readMap();
  return typeof entries[token] === 'string' ? entries[token] : '';
};
