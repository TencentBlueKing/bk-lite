'use client';

import { Button, Space, Typography } from 'antd';
import PanelShell from '@/components/panel-shell';
import { useCopy } from '@/hooks/useCopy';
import { useTranslation } from '@/utils/i18n';

export interface CustomReportingTokenDisplayProps {
  token?: string | null;
  variant?: 'inline' | 'panel';
  showCopyButton?: boolean;
}

const CustomReportingTokenDisplay = ({
  token,
  variant = 'inline',
  showCopyButton = false,
}: CustomReportingTokenDisplayProps) => {
  const { t } = useTranslation();
  const { copy } = useCopy();

  if (!token) {
    return null;
  }

  if (variant === 'panel') {
    return (
      <PanelShell
        className="rounded border border-[var(--color-border)] bg-[var(--color-bg)]"
        bodyClassName="space-y-3 p-[12px]"
      >
        <Space direction="vertical" className="flex">
          <Typography.Text copyable={{ text: token }}>
            {token}
          </Typography.Text>
          {showCopyButton ? (
            <Space>
              <Button size="small" onClick={() => copy(token)}>
                {t('CustomReporting.copyToken')}
              </Button>
            </Space>
          ) : null}
        </Space>
      </PanelShell>
    );
  }

  return (
    <Typography.Text copyable={{ text: token }}>
      {token}
    </Typography.Text>
  );
};

export default CustomReportingTokenDisplay;
