import React from 'react';
import { Modal, Button, List, Typography } from 'antd';
import type {
  MonitorSource,
  NetworkNodeLibraryItem,
} from '@/app/ops-analysis/types/networkTopology';
import { useTranslation } from '@/utils/i18n';

export interface MonitorSourcePickerModalProps {
  open: boolean;
  item: NetworkNodeLibraryItem | null;
  onCancel: () => void;
  onConfirm: (source: MonitorSource) => void;
  zIndex?: number;
  /** 测试 hook,可改名;不参与生产逻辑。 */
  testId?: string;
}

/**
 * 监控来源选择(design.md §3.2):
 * 当设备有多个 monitor_sources 时,弹出此 Modal 让用户消歧。
 * 单源设备不应触发此 Modal。
 */
const MonitorSourcePickerModal: React.FC<MonitorSourcePickerModalProps> = ({
  open,
  item,
  onCancel,
  onConfirm,
  zIndex,
  testId,
}) => {
  const { t } = useTranslation();
  const sources = item?.monitor_sources ?? [];

  return (
    <Modal
      title={t('opsAnalysis.networkTopology.monitorSourcePicker.title')}
      open={open}
      onCancel={onCancel}
      footer={null}
      destroyOnClose
      zIndex={zIndex}
      data-testid={testId}
    >
      {!item || sources.length === 0 ? (
        <Typography.Text type="secondary">
          {t('opsAnalysis.networkTopology.monitorSourcePicker.empty')}
        </Typography.Text>
      ) : (
        <List
          dataSource={sources}
          renderItem={(source) => (
            <List.Item>
              <List.Item.Meta
                title={
                  source.plugin_template_name ?? source.plugin_template_id
                }
                description={
                  source.plugin_group_name ?? source.plugin_group_id ?? ''
                }
              />
              <Button
                type={source.is_default ? 'primary' : 'default'}
                onClick={() => onConfirm(source)}
                data-testid={`${testId ?? 'monitor-source'}-choose-${source.network_collect_instance_id ?? ''}`}
              >
                {t('opsAnalysis.networkTopology.monitorSourcePicker.choose')}
              </Button>
            </List.Item>
          )}
        />
      )}
    </Modal>
  );
};

export default MonitorSourcePickerModal;
