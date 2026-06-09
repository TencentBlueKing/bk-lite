import React from 'react';
import { Form, Input, InputNumber, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';
import {
  arePacketbeatPortsValid,
  hasPacketbeatPorts
} from './packetbeatPortValidation';

const useFlowsPacketbeatFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (
      extra: {
        disabledFormItems?: Record<string, boolean>;
        hiddenFormItems?: Record<string, boolean>;
      } = {}
    ) => {
      const { disabledFormItems = {} } = extra;

      return (
        <>
          <div className="font-semibold mb-[8px]">
            {t('log.integration.packetbeatDeviceConfig')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.packetbeatDeviceConfigDesc')}
          </div>
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.packetbeatDevice')}
                  </span>
                  <Tooltip title={t('log.integration.packetbeatDeviceHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="device">
                  <Input
                    placeholder="any"
                    disabled={disabledFormItems.device}
                  />
                </Form.Item>
              </div>
            </Form.Item>
          </div>

          <div className="font-semibold mb-[8px]">
            {t('log.integration.httpTrafficCapture')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.httpTrafficCaptureDesc')}
          </div>
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.trafficCaptureEnabled')}
                  </span>
                </div>
                <Form.Item
                  className="mb-0"
                  name="enable_http"
                  valuePropName="checked"
                >
                  <Switch disabled={disabledFormItems.enable_http} />
                </Form.Item>
              </div>
            </Form.Item>
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.httpListenPorts')}
                  </span>
                  <span className="text-red-500 ml-[2px]">*</span>
                  <Tooltip title={t('log.integration.httpListenPortsHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item
                  className="mb-0 flex-1"
                  name="ports"
                  rules={[
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        const enabled = getFieldValue('enable_http');
                        if (!enabled) {
                          return Promise.resolve();
                        }
                        if (!hasPacketbeatPorts(value)) {
                          return Promise.reject(new Error(t('common.required')));
                        }
                        if (!arePacketbeatPortsValid(value)) {
                          return Promise.reject(
                            new Error(t('log.integration.httpPortsInvalid'))
                          );
                        }
                        return Promise.resolve();
                      }
                    })
                  ]}
                >
                  <Select
                    mode="tags"
                    placeholder={t('log.integration.httpPortsPlaceholder')}
                    disabled={disabledFormItems.ports}
                    suffixIcon={null}
                    open={false}
                  />
                </Form.Item>
              </div>
            </Form.Item>
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.httpCaptureBody')}
                  </span>
                  <Tooltip title={t('log.integration.httpCaptureBodyHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item
                  className="mb-0"
                  name="capture_body"
                  valuePropName="checked"
                >
                  <Switch disabled={disabledFormItems.capture_body} />
                </Form.Item>
              </div>
            </Form.Item>
          </div>

          <div className="font-semibold mb-[8px]">
            {t('log.integration.flowsTrafficCapture')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.flowsTrafficCaptureDesc')}
          </div>

          {/* 表单区块 */}
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.trafficCaptureEnabled')}
                  </span>
                </div>
                <Form.Item
                  className="mb-0"
                  name="enable_tcp_udp"
                  valuePropName="checked"
                >
                  <Switch disabled={disabledFormItems.enable_tcp_udp} />
                </Form.Item>
              </div>
            </Form.Item>
            {/* 统计周期 */}
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.flowsStatisticsPeriod')}
                  </span>
                  <Tooltip
                    title={t('log.integration.flowsStatisticsPeriodHint')}
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="flows_period">
                  <InputNumber
                    className="w-full"
                    placeholder="10"
                    min={1}
                    precision={0}
                    addonAfter="s"
                    disabled={disabledFormItems.flows_period}
                  />
                </Form.Item>
              </div>
            </Form.Item>

            {/* 超时时间 */}
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.flowsTimeoutLabel')}
                  </span>
                  <Tooltip title={t('log.integration.flowsTimeoutHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="flows_timeout">
                  <InputNumber
                    className="w-full"
                    placeholder="30"
                    min={1}
                    precision={0}
                    addonAfter="s"
                    disabled={disabledFormItems.flows_timeout}
                  />
                </Form.Item>
              </div>
            </Form.Item>
          </div>
        </>
      );
    }
  };
};

export { useFlowsPacketbeatFormItems };
