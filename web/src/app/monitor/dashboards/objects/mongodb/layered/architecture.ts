export type MongoFormLabel = '单机' | '主从';
export type MongoRoleLabel = '主库' | '从库';

const PLACEHOLDERS = new Set(['', '--', '-', '—']);
const RS_ROLES = new Set(['primary', 'secondary', 'master', 'slave', 'replica', 'arbiter']);
const REPL_FORM_STATES = new Set([0, 1, 2, 3, 5, 6, 7, 8, 9, 10]);
const NODE_ROLE: Record<string, string> = {
  pri: 'primary',
  sec: 'secondary',
  arb: 'arbiter'
};

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

/** 对象角色优先。没有时才用上报的 PRI / SEC / ARB。不从实例名猜。 */
export const mongoObservedRole = (databaseRole: string, nodeType = '') => {
  const role = roleToken(databaseRole);
  if (role) return role;
  return NODE_ROLE[roleToken(nodeType)] || '';
};

/**
 * 名含 standalone / single 时形态钉成单机。
 * 否则认对象角色，或副本状态读数。不从名字猜主从或集群。
 */
export const mongoForm = (
  nameText: string,
  databaseRole: string,
  replState: number | null = null
): MongoFormLabel | null => {
  if (hasAsciiToken(nameText, 'standalone') || hasAsciiToken(nameText, 'single')) return '单机';
  const role = roleToken(databaseRole);
  if (role === 'standalone' || role === 'single') return '单机';
  if (RS_ROLES.has(role)) return '主从';
  if (replState != null && REPL_FORM_STATES.has(replState)) return '主从';
  return null;
};

/** 主 / 从只认明确角色或副本状态 1 / 2。仲裁者、单机和空值都不挂角色胶囊。 */
export const mongoRole = (
  databaseRole: string,
  replState: number | null = null
): MongoRoleLabel | null => {
  const role = roleToken(databaseRole);
  if (role === 'primary' || role === 'master') return '主库';
  if (role === 'secondary' || role === 'slave' || role === 'replica') return '从库';
  if (role) return null;
  if (replState === 1) return '主库';
  if (replState === 2) return '从库';
  return null;
};

/** 副本状态读数对应的角色短词。认不出的码不编中文。 */
export const mongoReplicaStateLabel = (state: number | null): string => {
  if (state === 1) return '主库';
  if (state === 2) return '从库';
  if (state === 7) return '仲裁';
  if (state === 3) return '恢复中';
  if (state === 8) return '离线';
  if (state === 9) return '回滚中';
  if (state === 0 || state === 5) return '启动中';
  if (state === 10) return '已移出';
  return '';
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
  node_type?: unknown;
  summary_facts?: {
    database_role?: unknown;
    version?: unknown;
    port?: unknown;
    node_type?: unknown;
  } | null;
}) => {
  const facts = item.summary_facts && typeof item.summary_facts === 'object' ? item.summary_facts : {};
  return {
    databaseRole: factText(item.database_role ?? facts.database_role),
    nodeType: factText(item.node_type ?? facts.node_type),
    version: factText(item.version ?? facts.version),
    port: factText(item.port ?? facts.port)
  };
};
