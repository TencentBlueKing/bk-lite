'use client';

import React, { useEffect, useState } from 'react';
import { Empty, Form, Select, Steps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSourceApi } from '@/app/alarm/api/integration';
import { SnmpTrapNodeItem } from '@/app/alarm/types/integration';

const SnmpTrapGuide: React.FC = () => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const { getAlertSnmpTrapNodeList } = useSourceApi();
  const [nodeList, setNodeList] = useState<SnmpTrapNodeItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedNodeIp, setSelectedNodeIp] = useState<string>('');

  useEffect(() => {
    getNodeList();
  }, []);

  const getNodeList = async () => {
    setLoading(true);
    try {
      const data = await getAlertSnmpTrapNodeList({
        cloud_region_id: 0,
        page: 1,
        page_size: -1,
        is_container: true,
        is_active: true,
      });
      const nodes = data.nodes || [];
      setNodeList(nodes);
      if (nodes.length > 0) {
        const firstNode = nodes[0];
        form.setFieldsValue({ node_id: firstNode.id });
        setSelectedNodeIp(firstNode.ip || '');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleNodeChange = (value: number | string) => {
    const selectedNode = nodeList.find((node) => node.id === value);
    setSelectedNodeIp(selectedNode?.ip || '');
  };

  return (
    <div className="px-[10px] py-4 max-h-[calc(100vh-330px)] overflow-y-auto">
      <Form
        form={form}
        name="alarmSnmpTrapForm"
        layout="vertical"
        className="w-full"
      >
        <Form.Item label={t('integration.node')} required>
          <Form.Item
            noStyle
            name="node_id"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Select
              style={{ width: 600 }}
              className="mr-[10px]"
              placeholder={t('common.selectMsg')}
              loading={loading}
              onChange={handleNodeChange}
              options={nodeList.map((node) => ({
                label: `${node.name} (${node.ip})`,
                value: node.id,
              }))}
            />
          </Form.Item>
          <span className="text-[12px] text-[var(--color-text-3)]">
            {t('integration.snmpTrapNodeDes')}
          </span>
        </Form.Item>

        {!loading && nodeList.length === 0 ? (
          <Empty description={t('common.noData')} />
        ) : null}

        {selectedNodeIp ? (
          <div className="w-full bg-[var(--color-fill-1)] p-[20px]">
            <div className="mb-[10px] text-[16px] font-bold">
              {t('integration.snmpTrapAccessGuide')}
            </div>
            <Steps
              direction="vertical"
              current={1}
              items={[
                {
                  status: 'process',
                  title: t('integration.snmpTrapStep1'),
                  description: (
                    <div>
                      <div className="mb-[10px] text-[12px] text-[var(--color-text-3)]">
                        {t('integration.snmpTrapStep1Des')}
                      </div>
                      <div className="mt-[10px] bg-[var(--color-bg-1)] p-[10px]">
                        <div className="mb-[10px] border-b border-[var(--color-border-1)] pb-[10px]">
                          <span className="text-[12px] text-[var(--color-text-3)]">
                            {t('integration.snmpTrapTargetIp')}:
                          </span>
                          <span className="ml-[10px] font-mono font-semibold text-[var(--color-primary)]">
                            {t('integration.snmpTrapTargetIpValue')}
                          </span>
                        </div>
                        <div>
                          <span className="text-[12px] text-[var(--color-text-3)]">
                            {t('integration.snmpTrapTargetPort')}:
                          </span>
                          <span className="ml-[10px] font-mono font-semibold text-[var(--color-primary)]">
                            162
                          </span>
                        </div>
                      </div>
                    </div>
                  ),
                },
                {
                  status: 'process',
                  title: t('integration.snmpTrapStep2'),
                  description: (
                    <div>
                      <div className="mb-[10px] text-[12px] text-[var(--color-text-3)]">
                        {t('integration.snmpTrapStep2Des')}
                      </div>
                      <div className="mt-[10px] bg-[var(--color-bg-1)] p-[10px]">
                        <div>
                          <span className="text-[12px] text-[var(--color-text-3)]">
                            {t('integration.snmpTrapMibPath')}:
                          </span>
                          <span className="ml-[10px] font-mono font-semibold text-[var(--color-primary)]">
                            /usr/share/mibs
                          </span>
                        </div>
                      </div>
                    </div>
                  ),
                },
              ]}
            />
          </div>
        ) : null}
      </Form>
    </div>
  );
};

export default SnmpTrapGuide;
