'use client';

import React from 'react';
import Image from 'next/image';
import Link from 'next/link';

export interface PageStatusProps {
  code?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  actionHref?: string;
  actionLabel?: React.ReactNode;
  imageSrc?: string;
  imageAlt?: string;
  className?: string;
}

const PageStatus: React.FC<PageStatusProps> = ({
  code,
  title,
  description,
  actionHref,
  actionLabel,
  imageSrc = '/page-tip.gif',
  imageAlt = 'Page status illustration',
  className = '',
}) => {
  return (
    <div
      className={[
        'mx-auto flex w-full max-w-[850px] items-center justify-center text-left',
        className,
      ].filter(Boolean).join(' ')}
    >
      <div className="flex w-1/2 flex-col items-start">
        {code ? (
          <div className="text-[22px] font-mono font-bold uppercase leading-none md:text-[calc(4rem+2vw)]">
            {code}
          </div>
        ) : null}
        <div className={`${code ? 'mt-6' : ''} text-base text-[var(--color-text-1)]`}>
          {title}
        </div>
        {description ? (
          <div className="mt-3 text-sm leading-6 text-[var(--color-text-3)]">
            {description}
          </div>
        ) : null}
        {actionHref && actionLabel ? (
          <Link
            href={actionHref}
            className="mt-8 text-base text-[var(--color-primary)] hover:underline"
          >
            {actionLabel}
          </Link>
        ) : null}
      </div>

      <div className="flex w-1/2 justify-center">
        <Image
          src={imageSrc}
          alt={imageAlt}
          width={400}
          height={400}
          className="rounded"
        />
      </div>
    </div>
  );
};

export default PageStatus;
