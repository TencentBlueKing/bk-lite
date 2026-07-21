'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Tabs, Alert, Spin } from 'antd';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCollectApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import { useCollectToolApi } from '@/app/cmdb/api/collectTool';
import Introduction from '@/app/cmdb/components/introduction';
import type { CollectToolPrefillResponse, Protocol } from '@/app/cmdb/types/collectTool';
import SnmpTool from './components/snmpDebugTool';
import IpmiTool from './components/ipmiDebugTool';

interface AccessPointOption {
  value: string;
  label: string;
}

const CollectionToolPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const collectApi = useCollectApi();
  const { getCollectToolPrefill } = useCollectToolApi();

  const protocolParam = searchParams.get('protocol') as Protocol | null;
  const taskIdParam = searchParams.get('sourceTaskId') || searchParams.get('taskId');
  const [taskId, setTaskId] = useState<number | undefined>(
    taskIdParam ? parseInt(taskIdParam, 10) : undefined
  );

  const [activeTab, setActiveTab] = useState<string>(
    protocolParam === 'ipmi' ? 'ipmi' : 'snmp'
  );
  const [prefillData, setPrefillData] = useState<CollectToolPrefillResponse | null>(null);
  const [prefillLoading, setPrefillLoading] = useState(false);
  const [prefillWarning, setPrefillWarning] = useState<string | null>(null);
  const [accessPointOptions, setAccessPointOptions] = useState<
    AccessPointOption[]
  >([]);
  const isStrippingTaskIdRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    collectApi
      .getCollectNodes({
        page: 1,
        page_size: 10000,
        name: '',
      })
      .then((data: any) => {
        if (cancelled) {
          return;
        }

        const list = data?.nodes || [];
        const options = (Array.isArray(list) ? list : [])
          .filter((node: any) => node?.node_type === 'container')
          .map((node: any) => ({
            value: String(node.id),
            label: node.name,
          }));
        setAccessPointOptions(options);
      })
      .catch(() => {
        if (!cancelled) {
          setAccessPointOptions([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!taskIdParam) {
      if (isStrippingTaskIdRef.current) {
        isStrippingTaskIdRef.current = false;
        return;
      }

      setTaskId(undefined);
      return;
    }

    const parsedTaskId = parseInt(taskIdParam, 10);
    if (!Number.isNaN(parsedTaskId)) {
      setTaskId(parsedTaskId);
    } else {
      setTaskId(undefined);
    }

    const params = new URLSearchParams(searchParams.toString());
    params.delete('sourceTaskId');
    params.delete('taskId');
    const next = params.toString();
    isStrippingTaskIdRef.current = true;
    router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
  }, [pathname, router, searchParams, taskIdParam]);

  useEffect(() => {
    setActiveTab(protocolParam === 'ipmi' ? 'ipmi' : 'snmp');
  }, [protocolParam]);

  useEffect(() => {
    if (!taskId || !protocolParam) {
      setPrefillData(null);
      setPrefillWarning(null);
      setPrefillLoading(false);
      return;
    }

    setPrefillLoading(true);
    setPrefillData(null);
    setPrefillWarning(null);
    getCollectToolPrefill(taskId, protocolParam)
      .then((res: any) => {
        const data = res as CollectToolPrefillResponse;
        if (data.can_prefill) {
          setPrefillData(data);
        } else {
          setPrefillData(null);
          setPrefillWarning(t('CollectTool.cannotPrefill'));
        }
      })
      .catch(() => {
        setPrefillData(null);
        setPrefillWarning(t('CollectTool.cannotPrefill'));
      })
      .finally(() => {
        setPrefillLoading(false);
      });
  }, [protocolParam, taskId]);

  const tabItems = [
    {
      key: 'snmp',
      label: t('CollectTool.snmpTool'),
      children: (
        <Spin spinning={prefillLoading}>
          {prefillWarning && activeTab === 'snmp' && (
            <Alert
              type="warning"
              message={prefillWarning}
              className="mb-4"
              showIcon
              closable
            />
          )}
          <SnmpTool
            accessPointOptions={accessPointOptions}
            prefill={
              activeTab === 'snmp' && prefillData?.protocol === 'snmp'
                ? prefillData.prefill
                : undefined
            }
            taskId={taskId}
          />
        </Spin>
      ),
    },
    {
      key: 'ipmi',
      label: t('CollectTool.ipmiTool'),
      children: (
        <Spin spinning={prefillLoading}>
          {prefillWarning && activeTab === 'ipmi' && (
            <Alert
              type="warning"
              message={prefillWarning}
              className="mb-4"
              showIcon
              closable
            />
          )}
          <IpmiTool
            accessPointOptions={accessPointOptions}
            prefill={
              activeTab === 'ipmi' && prefillData?.protocol === 'ipmi'
                ? prefillData.prefill
                : undefined
            }
            taskId={taskId}
          />
        </Spin>
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Introduction
        title={t('CollectTool.pageTitle')}
        message={t('CollectTool.pageDesc')}
      />
      <div className="min-h-0 flex-1 overflow-hidden pb-4">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          className="flex h-full min-h-0 flex-col [&_.ant-spin-nested-loading]:h-full [&_.ant-spin-container]:h-full [&_.ant-tabs-content]:h-full [&_.ant-tabs-content-holder]:min-h-0 [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-tabpane]:min-h-0 [&_.ant-tabs-tabpane]:pt-2"
        />
      </div>
    </div>
  );
};

export default CollectionToolPage;
