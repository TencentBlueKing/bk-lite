'use client';

import React from 'react';
import { Collapse } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { RESERVED_SCRIPT_TAG_KEYS } from './scriptMetricsParser';
import { SCRIPT_PROM_TEXT_EXAMPLE } from './scriptCollectDemos';

const GUIDE_COLLAPSE_CLASS =
  'mb-2 max-w-[640px] bg-transparent [&_.ant-collapse-header]:!items-center [&_.ant-collapse-header]:!px-0 [&_.ant-collapse-expand-icon]:!me-2 [&_.ant-collapse-content-box]:!px-0 [&_.ant-collapse-content-box]:!pb-1 [&_.ant-collapse-content-box]:!pt-2';

const ScriptCollectGuide: React.FC = () => {
  const { t } = useTranslation();
  const reservedTags = Array.from(RESERVED_SCRIPT_TAG_KEYS).join(', ');

  return (
    <Collapse
      bordered={false}
      ghost
      className={GUIDE_COLLAPSE_CLASS}
      expandIconPosition="start"
      items={[
        {
          key: 'script-guide',
          label: (
            <span className="text-[13px] font-medium leading-5 text-[var(--color-text-1)]">
              {t('monitor.integrations.scriptGuideTitle', '编写指南')}
            </span>
          ),
          children: (
            <div className="space-y-3 text-[12px] leading-[18px] text-[var(--color-text-2)]">
              <section>
                <div className="font-medium text-[var(--color-text-1)]">
                  {t('monitor.integrations.scriptGuideFormatTitle', '输出格式')}
                </div>
                <p className="mt-1 mb-0">
                  {t(
                    'monitor.integrations.scriptGuideFormatBody',
                    '标准输出必须是 Prometheus 文本，一行一个样本，例如 {example}。最多 50 条。行尾时间戳会被忽略。',
                    { example: SCRIPT_PROM_TEXT_EXAMPLE }
                  )}
                </p>
              </section>
              <section>
                <div className="font-medium text-[var(--color-text-1)]">
                  {t('monitor.integrations.scriptGuideEnvTitle', '环境变量')}
                </div>
                <p className="mt-1 mb-0">
                  {t(
                    'monitor.integrations.scriptGuideEnvBody',
                    '在「环境变量」中填写 KEY 和 VALUE。Linux 读取 $KEY，Windows 读取 $env:KEY，Python 读取 os.environ.get("KEY")。'
                  )}
                </p>
              </section>
              <section>
                <div className="font-medium text-[var(--color-text-1)]">
                  {t('monitor.integrations.scriptGuideReservedTitle', '保留标签')}
                </div>
                <p className="mt-1 mb-0">
                  {t(
                    'monitor.integrations.scriptGuideReservedBody',
                    '以下标签由平台写入；脚本即使输出同名标签也会被覆盖，请改用其它标签名：{tags}',
                    { tags: reservedTags }
                  )}
                </p>
              </section>
              <section>
                <div className="font-medium text-[var(--color-text-1)]">
                  {t('monitor.integrations.scriptGuideLimitsTitle', '限制')}
                </div>
                <ul className="mt-1 mb-0 list-disc space-y-1 pl-4">
                  <li>
                    {t(
                      'monitor.integrations.scriptGuideLimitOs',
                      '只能绑定操作系统类监控对象'
                    )}
                  </li>
                  <li>
                    {t(
                      'monitor.integrations.scriptGuideLimitInterval',
                      '采集间隔不能小于 60 秒'
                    )}
                  </li>
                  <li>
                    {t(
                      'monitor.integrations.scriptGuideLimitTimeout',
                      '超时按采集间隔减 1 秒执行，不能更长'
                    )}
                  </li>
                  <li>
                    {t(
                      'monitor.integrations.scriptGuideLimitRoot',
                      'Linux 上不能以 root 用户运行'
                    )}
                  </li>
                  <li>
                    {t(
                      'monitor.integrations.scriptGuideLimitInterpreter',
                      '解释器只能从白名单选择：Linux 为 /bin/sh、/bin/bash、/usr/bin/python3，Windows 为 powershell.exe、cmd.exe、python.exe'
                    )}
                  </li>
                  <li>
                    {t(
                      'monitor.integrations.scriptGuideLimitMetricPrefix',
                      '指标名不能以 bklite_script_ 开头'
                    )}
                  </li>
                </ul>
              </section>
            </div>
          )
        }
      ]}
    />
  );
};

export default ScriptCollectGuide;
