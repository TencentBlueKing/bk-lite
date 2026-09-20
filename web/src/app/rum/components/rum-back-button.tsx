'use client';

import type { MouseEventHandler, ReactNode } from 'react';
import Link from 'next/link';
import { ArrowLeftOutlined } from '@ant-design/icons';

import { useTranslation } from '@/utils/i18n';

/** RUM 详情统一返回：标题左侧纯图标（强制贴在 title 左边）。 */
export default function RumBackButton({
  href,
  onClick,
  disabled,
  className,
}: {
  href?: string;
  onClick?: MouseEventHandler<HTMLElement>;
  disabled?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  const label = t('rum.common.back', '返回');
  const icon = (
    <span
      role="img"
      aria-hidden="true"
      className="inline-flex text-base leading-none text-[var(--color-text-2)]"
    >
      <ArrowLeftOutlined />
    </span>
  );
  const sharedClass = [
    'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md',
    'text-[var(--color-text-2)] transition-colors',
    'hover:bg-[var(--color-fill-1)] hover:text-[var(--color-text-1)]',
    'disabled:cursor-not-allowed disabled:opacity-40',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  if (href) {
    return (
      <Link href={href} aria-label={label} className={sharedClass} onClick={onClick}>
        {icon}
      </Link>
    );
  }

  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={sharedClass}
    >
      {icon}
    </button>
  );
}

/** 详情页头左侧：返回图标紧贴标题。 */
export function RumDetailTitle({
  title,
  backHref,
  onBack,
  afterTitle,
  subtitle,
  titleClassName,
}: {
  title: ReactNode;
  backHref?: string;
  onBack?: MouseEventHandler<HTMLElement>;
  afterTitle?: ReactNode;
  subtitle?: ReactNode;
  titleClassName?: string;
}) {
  return (
    <div className="flex min-w-0 items-center gap-1">
      <RumBackButton href={backHref} onClick={onBack} />
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {typeof title === 'string' || typeof title === 'number' ? (
            <h1
              className={[
                'm-0 truncate text-lg font-semibold text-[var(--color-text-1)]',
                titleClassName,
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {title}
            </h1>
          ) : (
            title
          )}
          {afterTitle}
        </div>
        {subtitle ? <div className="mt-0.5 text-xs text-[var(--color-text-3)]">{subtitle}</div> : null}
      </div>
    </div>
  );
}
