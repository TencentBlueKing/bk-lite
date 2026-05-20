'use client';
import React, { useState } from 'react';
import { Steps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import K8sTaskForm from '../k8sTask';
import CollectorInstall from './collectorInstall';
import AccessComplete from './accessComplete';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';

interface Props {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

/**
 * CMDB k8s 引导式接入容器：
 *   Step 1 接入配置 → 复用既有 K8sTaskForm + 新增 collector_cluster_id / cloud_region_id
 *   Step 2 采集器安装 → 调 CMDB 自己的 install_token / open render / verify 接口
 *   Step 3 接入完成 → 提示采集器已就绪、CMDB 落图按计划进行
 *
 * 编辑态保持单步：直接渲染 K8sTaskForm，避免影响既有运维流程。
 */
const K8sGuidedTask: React.FC<Props> = ({
  onClose,
  onSuccess,
  selectedNode,
  modelItem,
  editId,
}) => {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [collectorClusterId, setCollectorClusterId] = useState('');
  const [cloudRegionId, setCloudRegionId] = useState<number | string>('');

  if (editId) {
    // 编辑保留原表单体验
    return (
      <K8sTaskForm
        onClose={onClose}
        onSuccess={onSuccess}
        selectedNode={selectedNode}
        modelItem={modelItem}
        editId={editId}
      />
    );
  }

  const steps = [
    { title: t('Collection.k8sTask.accessConfig') || 'Access Config' },
    { title: t('Collection.k8sTask.collectorInstall') || 'Collector Install' },
    { title: t('Collection.k8sTask.accessComplete') || 'Complete' },
  ];

  return (
    <div className="w-full">
      <div className="mb-6 px-2">
        <Steps current={step} size="default">
          {steps.map((s, idx) => (
            <Steps.Step key={idx} title={s.title} />
          ))}
        </Steps>
      </div>
      <div>
        {step === 0 && (
          <K8sTaskForm
            onClose={onClose}
            onSuccess={onSuccess}
            selectedNode={selectedNode}
            modelItem={modelItem}
            onAfterSave={({ collector_cluster_id, cloud_region_id }) => {
              setCollectorClusterId(collector_cluster_id);
              setCloudRegionId(cloud_region_id);
              setStep(1);
              return true; // 接管后续流程，阻止默认关闭
            }}
          />
        )}
        {step === 1 && (
          <CollectorInstall
            collectorClusterId={collectorClusterId}
            cloudRegionId={cloudRegionId}
            onPrev={() => setStep(0)}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && (
          <AccessComplete
            onClose={onClose}
            onReset={() => {
              setStep(0);
              setCollectorClusterId('');
              setCloudRegionId('');
            }}
          />
        )}
      </div>
    </div>
  );
};

export default K8sGuidedTask;
