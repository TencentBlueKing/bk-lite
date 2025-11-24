'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { useRouter } from 'next/navigation';
import { Button, Tabs } from 'antd';
import OperateDrawer from '@/app/monitor/components/operate-drawer';
import { ModalRef, TabItem, ChartProps, ObjectItem } from '@/app/monitor/types';
import { ViewModalProps } from '@/app/monitor/types/view';
import { useTranslation } from '@/utils/i18n';
import MonitorView from './monitorView';
import MonitorAlarm from './monitorAlarm';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { INIT_VIEW_MODAL_FORM } from '@/app/monitor/constants/view';

const ViewModal = forwardRef<ModalRef, ViewModalProps>(
  ({ monitorObject, monitorName, plugins, metrics, objects = [] }, ref) => {
    const { t } = useTranslation();
    const router = useRouter();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [title, setTitle] = useState<string>('');
    const [viewConfig, setViewConfig] =
      useState<ChartProps>(INIT_VIEW_MODAL_FORM);
    const tabs: TabItem[] = [
      {
        label: t('monitor.views.monitorView'),
        key: 'monitorView',
      },
      {
        label: t('monitor.views.alertList'),
        key: 'alertList',
      },
    ];
    const [currentTab, setCurrentTab] = useState<string>('monitorView');
    const rightSlot = (
      <Button
        type="link"
        className="relative bottom-0 right-0"
        onClick={() => linkToDetial()}
      >
        {t('monitor.views.viewDashboard')}
      </Button>
    );

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form }) => {
        // 开启弹窗的交互
        setGroupVisible(true);
        setTitle(title);
        setViewConfig(form as ChartProps);
      },
    }));

    const changeTab = (val: string) => {
      setCurrentTab(val);
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setCurrentTab('monitorView');
      setViewConfig(INIT_VIEW_MODAL_FORM);
    };

    const linkToDetial = () => {
      const monitorItem = objects.find(
        (item: ObjectItem) => item.id === monitorObject
      );
      const row: any = {
        monitorObjId: monitorObject || '',
        name: monitorName,
        monitorObjDisplayName: monitorItem?.display_name || '',
        icon: monitorItem?.icon || OBJECT_DEFAULT_ICON,
        instance_id: viewConfig.instance_id,
        instance_name: viewConfig.instance_name,
        instance_id_values: viewConfig.instance_id_values,
      };
      const params = new URLSearchParams(row);
      const targetUrl = `/monitor/view/detail?${params.toString()}`;
      router.push(targetUrl);
    };

    return (
      <div>
        <OperateDrawer
          width={950}
          title={title}
          subTitle={viewConfig.instance_name}
          visible={groupVisible}
          destroyOnClose
          footer={
            <div>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
          onClose={handleCancel}
        >
          <Tabs
            activeKey={currentTab}
            items={tabs}
            onChange={changeTab}
            tabBarExtraContent={rightSlot}
          />
          {currentTab === 'monitorView' ? (
            <MonitorView
              monitorObject={monitorObject}
              monitorName={monitorName}
              plugins={plugins}
              form={viewConfig}
            />
          ) : (
            <MonitorAlarm
              monitorObject={monitorObject}
              monitorName={monitorName}
              plugins={plugins}
              form={viewConfig}
              metrics={metrics}
              objects={objects}
            />
          )}
        </OperateDrawer>
      </div>
    );
  }
);
ViewModal.displayName = 'ViewModal';
export default ViewModal;
