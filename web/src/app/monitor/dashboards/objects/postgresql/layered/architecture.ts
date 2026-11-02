export type PostgresFormLabel = '集群' | '主从' | '单机';
export type PostgresRoleLabel = '主库' | '备库';

const PLACEHOLDERS = new Set(['', '--', '-']);

const hasAsciiToken = (text: string, token: string) => (
  new RegExp(`(?:^|[^a-z0-9])${token}(?:[^a-z0-9]|$)`, 'i').test(text)
);

/** 展示名和标识拼在一起。占位符「--」不当成名字。 */
export const postgresIdentityText = (
  ...parts: Array<string | number | null | undefined>
) => parts
  .map((part) => String(part ?? '').trim())
  .filter((part) => !PLACEHOLDERS.has(part))
  .join(' ');

/**
 * 只从对象名/标识取形态。cluster / ha → 集群；
 * replica、primary-standby、主从 → 主从；standalone / single → 单机。
 * 短词按边界匹配，避免 shanghai 被看成 ha。
 */
export const postgresFormFromName = (text: string): PostgresFormLabel | null => {
  if (hasAsciiToken(text, 'cluster') || hasAsciiToken(text, 'ha')) return '集群';
  const lower = text.toLowerCase();
  if (
    lower.includes('primary-standby')
    || text.includes('主从')
    || hasAsciiToken(text, 'replica')
  ) {
    return '主从';
  }
  if (hasAsciiToken(text, 'standalone') || hasAsciiToken(text, 'single')) return '单机';
  return null;
};

/**
 * 名字已经给出集群、主从或单机时，形态钉住，角色另算。
 * 没有这些名字时，采到 recovery 才是主从。
 * 查询未回时不把空名提前定成主从。
 */
export const visiblePostgresForm = (
  nameForm: PostgresFormLabel | null,
  recoveryPresent: boolean,
  pending: boolean
): PostgresFormLabel | null => {
  if (nameForm === '集群' || nameForm === '主从' || nameForm === '单机') return nameForm;
  if (pending) return null;
  if (recoveryPresent) return '主从';
  return nameForm;
};

/** 0 主库（含单机写库），1 备库。其它读数或没有采点不挂角色。 */
export const postgresRoleLabel = (
  value: number | null | undefined
): PostgresRoleLabel | null => {
  if (value == null || !Number.isFinite(value)) return null;
  if (Math.abs(value) < 1e-6) return '主库';
  if (Math.abs(value - 1) < 1e-6) return '备库';
  return null;
};
