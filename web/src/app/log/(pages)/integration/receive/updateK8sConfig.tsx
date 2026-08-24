'use client';

import { ModalRef, ModalProps, TableDataItem } from '@/app/log/types';
import { Alert, Button, Form, Select, Spin } from 'antd';
import React, {
  useState,
  useImperativeHandle,
  forwardRef
} from 'react';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import CodeEditor from '@/components/code-editor';
import useLogApi from '@/app/log/api/integration';
import CollectSettingFields from '../list/detail/configure/k8s/collectSettingFields';

interface CloudRegionItem {
  id: React.Key;
  name?: string;
}

const UpdateK8sConfig = forwardRef<ModalRef, ModalProps>(({ onSuccess }, ref) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const {
    getCloudRegionList,
    getK8sCollectSetting,
    saveK8sCollectSetting
  } = useLogApi();
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [formData, setFormData] = useState<TableDataItem>({});
  const [settingUnknown, setSettingUnknown] = useState(false);
  const [dockerPathForFields, setDockerPathForFields] = useState<string>();
  const [cloudRegionList, setCloudRegionList] = useState<CloudRegionItem[]>([]);
  const [command, setCommand] = useState('');

  useImperativeHandle(ref, () => ({
    showModal: ({ form: row }) => {
      setFormData(row);
      setModalVisible(true);
      setConfirmLoading(false);
      setCommand('');
      setSettingUnknown(false);
      form.resetFields();
      void load(row);
    }
  }));

  const load = async (row: TableDataItem) => {
    setPageLoading(true);
    try {
      const [regions, setting] = await Promise.all([
        getCloudRegionList(),
        getK8sCollectSetting(String(row.id))
      ]);
      setCloudRegionList(regions || []);
      if (setting?.unknown) {
        setSettingUnknown(true);
        setDockerPathForFields(undefined);
        form.setFieldsValue({
          runtime_profile: undefined,
          host_log_path: undefined,
          docker_container_log_path: undefined,
          namespace_patterns: undefined,
          pod_patterns: undefined
        });
        return;
      }
      setSettingUnknown(false);
      setDockerPathForFields(setting?.docker_container_log_path);
      form.setFieldsValue({
        runtime_profile: setting?.runtime_profile,
        host_log_path: setting?.host_log_path,
        docker_container_log_path: setting?.docker_container_log_path,
        namespace_patterns: (setting?.namespace_patterns || []).join('\n'),
        pod_patterns: (setting?.pod_patterns || []).join('\n')
      });
    } finally {
      setPageLoading(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setModalVisible(false);
    setCommand('');
    setPageLoading(false);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    setConfirmLoading(true);
    try {
      const result = await saveK8sCollectSetting({
        instance_id: String(formData.id),
        cloud_region_id: values.cloud_region_id,
        runtime_profile: values.runtime_profile,
        host_log_path: values.host_log_path,
        docker_container_log_path: values.docker_container_log_path,
        namespace_patterns: values.namespace_patterns,
        pod_patterns: values.pod_patterns
      });
      setCommand(result?.command || '');
      onSuccess?.();
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <OperateModal
      width={760}
      title={t('log.integration.updateConfigration')}
      visible={modalVisible}
      onCancel={handleCancel}
      footer={
        command ? (
          <Button onClick={handleCancel}>{t('common.close')}</Button>
        ) : (
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              loading={confirmLoading}
              disabled={pageLoading}
              onClick={() => {
                void handleSubmit();
              }}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        )
      }
    >
      <Spin spinning={pageLoading}>
        {command ? (
          <div>
            <Alert
              type="info"
              showIcon
              className="mb-4"
              message={t('log.integration.k8s.applyRequiredTitle')}
              description={t('log.integration.k8s.applyRequiredDesc')}
            />
            <CodeEditor
              mode="shell"
              theme="monokai"
              name="k8s-update-command"
              width="100%"
              height="120px"
              readOnly
              value={command}
              headerOptions={{ copy: true }}
            />
          </div>
        ) : (
          <Form form={form} layout="vertical">
            <Form.Item
              name="cloud_region_id"
              label={t('log.integration.k8s.cloudRegion')}
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Select
                placeholder={t('log.integration.k8s.selectCloudRegion')}
                options={cloudRegionList.map((item) => ({
                  label: item.name || item.id,
                  value: item.id
                }))}
              />
            </Form.Item>
            <CollectSettingFields
              unknown={settingUnknown}
              initialDockerPath={dockerPathForFields}
            />
          </Form>
        )}
      </Spin>
    </OperateModal>
  );
});

UpdateK8sConfig.displayName = 'UpdateK8sConfig';

export default UpdateK8sConfig;
