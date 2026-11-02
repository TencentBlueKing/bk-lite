'use client';

const chipClass = (
  'inline-flex h-5 shrink-0 items-center rounded-full border border-[color-mix(in_srgb,var(--color-primary)_32%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-primary)_10%,var(--color-bg))] px-2 text-[12px] font-medium leading-none text-[var(--color-text-1)]'
);

/**
 * 形态与角色并列，样式与 Redis 架构芯片同一套。
 * 没有 recovery/role 采点，角色固定为「—」，不用实例名猜主备。
 */
export function PostgresIdentityPills() {
  return (
    <span className="inline-flex h-5 max-w-full items-center gap-1" data-postgres-identity="">
      <span className={chipClass} data-postgres-form="instance">实例</span>
      <span className={chipClass} data-postgres-role="empty" title="角色暂无">—</span>
    </span>
  );
}
