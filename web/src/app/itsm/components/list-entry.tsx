'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';

interface ItsmListEntryProps {
  children: ReactNode;
  href?: string;
  onClick?: () => void;
  onNavigate?: () => void;
  allowed?: boolean;
}

/** 名称仅承接现有入口；不把整行点击绑定到编辑或选择。 */
export function ItsmListEntry({ children, href, onClick, onNavigate, allowed = true }: ItsmListEntryProps) {
  if (!allowed || (!href && !onClick)) return <span>{children}</span>;
  const className = 'cursor-pointer text-left font-normal !text-[var(--color-text-1)] hover:!text-[var(--color-primary)] hover:underline focus-visible:!text-[var(--color-primary)] focus-visible:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]';
  if (href) return <Link href={href} className={className} onNavigate={onNavigate} onClick={event => event.stopPropagation()}>{children}</Link>;
  return <button type="button" className={className} onClick={event => { event.stopPropagation(); onClick?.(); }}>{children}</button>;
}
