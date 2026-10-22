'use client';

import React from 'react';
import { Button, Popover, Typography } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { getChannelColorGuide } from '@/app/alarm/utils/notificationTemplateColorGuide';

interface ChannelColorTipProps {
  channelType: string;
  onInsert: (text: string) => void;
}

export default function ChannelColorTip({ channelType, onInsert }: ChannelColorTipProps) {
  const { t } = useTranslation();
  const guide = getChannelColorGuide(channelType);

  return (
    <Popover
      trigger="click"
      placement="bottomLeft"
      content={(
        <div className="max-w-[380px]">
          <Typography.Text>{t(guide.introKey)}</Typography.Text>
          {guide.choices.length > 0 && (
            <div className="mt-2 flex flex-col gap-2">
              {guide.choices.map((choice) => (
                <div key={choice.snippet} className="flex items-start gap-2">
                  <span
                    className="mt-1 inline-block h-3 w-3 shrink-0 rounded-sm border border-[var(--color-border-2)]"
                    style={choice.swatch ? { background: choice.swatch } : undefined}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs">
                      <span className="font-mono">{choice.token}</span>
                      <Typography.Text type="secondary"> · {t(choice.usageKey)}</Typography.Text>
                    </div>
                    <code className="mt-1 block break-all text-xs">{choice.snippet}</code>
                  </div>
                  <Button
                    size="small"
                    type="link"
                    className="px-0"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => onInsert(choice.snippet)}
                  >
                    {t('settings.notificationTemplate.colorTipInsert')}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    >
      <Button size="small" icon={<InfoCircleOutlined />}>
        {t('settings.notificationTemplate.colorTip')}
      </Button>
    </Popover>
  );
}
