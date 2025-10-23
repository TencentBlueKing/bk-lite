import React from 'react';
import { Form, Checkbox, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';

const useSystemMetricbeatFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (
      extra: {
        disabledFormItems: Record<string, boolean>;
        mode?: string;
      } = {
        disabledFormItems: {},
        mode: 'edit',
      }
    ) => {
      return (
        <>
          <Form.Item
            className={
              extra.mode === 'auto' ? 'w-[calc(100vw-306px)] min-w-[600px]' : ''
            }
            label={t('log.integration.metricsets')}
            name="metricsets"
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <Checkbox.Group disabled={extra.disabledFormItems.metric_type}>
              <Space direction="vertical">
                <Checkbox value="cpu">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">CPU</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.cpuDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="load">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Load</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.loadDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="memory">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Memory</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.memoryDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="network">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Network</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.metricNetworkDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="process">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Process</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.processDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="process_summary">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">
                      Process Summary
                    </span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.processSummaryDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="uptime">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Uptime</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.uptimeDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="socket_summary">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">
                      Socket Summary
                    </span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.socketSummaryDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="core">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Core</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.coreDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="diskio">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Disk IO</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.diskIoDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="filesystem">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">File System</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.fileSystemDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="fsstat">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Fsstat</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.fsstatDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="raid">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Raid</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.raidDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="socket">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Socket</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.socketDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="service">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Service</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.serviceDes')}
                    </span>
                  </span>
                </Checkbox>
              </Space>
            </Checkbox.Group>
          </Form.Item>
        </>
      );
    },
  };
};

export { useSystemMetricbeatFormItems };
