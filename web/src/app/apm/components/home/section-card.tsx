'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { Button, Space, Typography } from 'antd';

const { Title, Text } = Typography;

interface SectionCardProps {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  viewAllHref?: string;
  viewAllLabel?: string;
  failed?: boolean;
  onRetry?: () => void;
  children: ReactNode;
}

export default function SectionCard({
  icon,
  title,
  subtitle,
  viewAllHref,
  viewAllLabel = '查看全部 →',
  failed = false,
  onRetry,
  children,
}: SectionCardProps) {
  return (
    <div className="h-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-6 py-5">
      <div className="mb-3 flex items-center justify-between">
        <Space size={8} align="center">
          {icon}
          <Title level={5} className="!mb-0 !font-semibold">
            {title}
          </Title>
          {subtitle ? (
            <Text type="secondary" className="text-xs">
              {subtitle}
            </Text>
          ) : null}
        </Space>
        {viewAllHref ? (
          <Link href={viewAllHref} className="text-[13px] text-[var(--color-primary)] hover:underline">
            {viewAllLabel}
          </Link>
        ) : null}
      </div>
      {failed ? (
        <div className="py-10 text-center">
          <Button type="link" onClick={onRetry}>
            加载失败，点击重试
          </Button>
        </div>
      ) : (
        children
      )}
    </div>
  );
}
