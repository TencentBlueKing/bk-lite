export type MongoFormLabel = '单机' | '主从';
export type MongoRoleLabel = '主库' | '从库';

const PLACEHOLDERS = new Set(['', '--', '-', '—']);
const RS_ROLES = new Set(['primary', 'secondary', 'master', 'slave', 'replica', 'arbiter']);

const hasAsciiToken = (text: string, token: string) => (
  new RegExp(`(?:^|[^a-z0-9])${token}(?:[^a-z0-9]|$)`, 'i').test(text)
);

/** 展示名和标识拼在一起。占位符不当成名字。 */
export const mongoIdentityText = (
  ...parts: Array<string | number | null | undefined>
) => parts
  .map((part) => String(part ?? '').trim())
  .filter((part) => !PLACEHOLDERS.has(part))
  .join(' ');

const roleToken = (databaseRole: string) => databaseRole.trim().toLowerCase();

/**
 * 名含 standalone / single 时形态钉成单机。
 * 否则只认对象上的 database_role：standalone 为单机，明确的副本集角色为主从。
 * 不从名字猜主从或集群。
 */
export const mongoForm = (nameText: string, databaseRole: string): MongoFormLabel | null => {
  if (hasAsciiToken(nameText, 'standalone') || hasAsciiToken(nameText, 'single')) return '单机';
  const role = roleToken(databaseRole);
  if (role === 'standalone' || role === 'single') return '单机';
  if (RS_ROLES.has(role)) return '主从';
  return null;
};

/** 主 / 从只认明确角色。单机、仲裁者和空值都不挂角色胶囊。 */
export const mongoRole = (databaseRole: string): MongoRoleLabel | null => {
  const role = roleToken(databaseRole);
  if (role === 'primary' || role === 'master') return '主库';
  if (role === 'secondary' || role === 'slave' || role === 'replica') return '从库';
  return null;
};

const factText = (value: unknown) => {
  const raw = String(value ?? '').trim();
  if (!raw || PLACEHOLDERS.has(raw)) return '';
  return raw;
};

/** 实例列表上已经带的事实。没有就不编。 */
export const readMongoInstanceFacts = (item: {
  database_role?: unknown;
  version?: unknown;
  port?: unknown;
  summary_facts?: { database_role?: unknown; version?: unknown; port?: unknown } | null;
}) => {
  const facts = item.summary_facts && typeof item.summary_facts === 'object' ? item.summary_facts : {};
  return {
    databaseRole: factText(item.database_role ?? facts.database_role),
    version: factText(item.version ?? facts.version),
    port: factText(item.port ?? facts.port)
  };
};
