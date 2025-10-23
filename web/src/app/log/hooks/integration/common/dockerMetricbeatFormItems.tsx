import React from 'react';
import { Form, Checkbox, Space, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';

const useDockerMetricbeatFormItems = () => {
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
            tooltip={t('log.integration.dockerHostsDes')}
            label={t('log.integration.dockerHosts')}
            required={true}
            name="hosts"
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <Select
              mode="tags"
              placeholder={t('log.integration.dockerHosts')}
              disabled={extra.disabledFormItems.hosts}
              suffixIcon={null}
              open={false}
            />
          </Form.Item>
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
                <Checkbox value="container">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Container</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.containerDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="cpu">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">CPU</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.cpuDes')}
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
                <Checkbox value="event">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Event</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.eventDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="healthcheck">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Healthcheck</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.healthcheckDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="info">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Info</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.infoDes')}
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
                      {t('log.integration.docherNetworkDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="image">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">Image</span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.imageDes')}
                    </span>
                  </span>
                </Checkbox>
                <Checkbox value="network_summary">
                  <span className="flex items-center">
                    <span className="w-[120px] min-w-[120px]">
                      Network Summary
                    </span>
                    <span className="text-[var(--color-text-3)] text-[12px]">
                      {t('log.integration.networkSummaryDes')}
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

export { useDockerMetricbeatFormItems };
