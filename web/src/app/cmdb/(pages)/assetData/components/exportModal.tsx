'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import axios from 'axios';
import OperateModal from '@/components/operate-modal';
import { Checkbox, Button, Spin, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
import { useSession } from 'next-auth/react';
import { useAuth } from '@/context/auth';
import {
  AssoFieldType,
  ModelItem,
  AssoTypeItem,
  ColumnItem,
} from '@/app/cmdb/types/assetManage';
import {
  RelationItem,
  ExportModalProps,
  ExportModalConfig,
  ExportModalRef,
} from '@/app/cmdb/types/assetData';

const ExportModal = forwardRef<ExportModalRef, ExportModalProps>(
  ({ models, assoTypes }, ref) => {
    const { t } = useTranslation();
    const { getModelAssociations } = useModelApi();
    const { data: session } = useSession();
    const authContext = useAuth();
    const token = session?.user?.token || authContext?.token || null;

    const [visible, setVisible] = useState(false);
    const [loading, setLoading] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [title, setTitle] = useState('');
    const [modelId, setModelId] = useState('');
    const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
    const [exportType, setExportType] = useState<
      'selected' | 'currentPage' | 'all'
    >('all');
    const [tableData, setTableData] = useState<any[]>([]);

    const [availableColumns, setAvailableColumns] = useState<ColumnItem[]>([]);
    const [selectedAttrs, setSelectedAttrs] = useState<string[]>([]);

    const [relationList, setRelationList] = useState<RelationItem[]>([]);
    const [selectedRelations, setSelectedRelations] = useState<string[]>([]);

    useImperativeHandle(ref, () => ({
      showModal: (config: ExportModalConfig) => {
        setVisible(true);
        setTitle(config.title);
        setModelId(config.modelId);
        setSelectedKeys(config.selectedKeys);
        setExportType(config.exportType);
        setTableData(config.tableData || []);

        const filteredColumns = config.columns.filter(
          (col) => col.key !== 'action'
        );
        setAvailableColumns(filteredColumns);

        setSelectedAttrs(filteredColumns.map((col) => col.key as string));

        fetchAssociations(config.modelId);
      },
    }));

    const fetchAssociations = async (modelId: string) => {
      setLoading(true);
      try {
        const associations = await getModelAssociations(modelId);
        const formattedRelations: RelationItem[] = associations.map(
          (item: AssoFieldType) => ({
            ...item,
            name: `${showModelName(item.src_model_id)}-${showConnectType(
              item.asst_id,
              'asst_name'
            )}-${showModelName(item.dst_model_id)}`,
            relation_key: `${item.src_model_id}_${item.asst_id}_${item.dst_model_id}`,
          })
        );
        setRelationList(formattedRelations);
        setSelectedRelations([]);
      } catch (error) {
        console.error('Failed to fetch associations:', error);
        setRelationList([]);
      } finally {
        setLoading(false);
      }
    };

    const showModelName = (id: string) => {
      return (
        models.find((item: ModelItem) => item.model_id === id)?.model_name ||
        '--'
      );
    };

    const showConnectType = (id: string, key: string) => {
      return (
        (assoTypes.find((item: AssoTypeItem) => item.asst_id === id) as any)?.[
          key
        ] || '--'
      );
    };

    const handleAttrSelectAll = (checked: boolean) => {
      if (checked) {
        setSelectedAttrs(availableColumns.map((col) => col.key as string));
      } else {
        setSelectedAttrs([]);
      }
    };

    const handleAttrChange = (checkedValues: string[]) => {
      setSelectedAttrs(checkedValues);
    };

    const handleRelationSelectAll = (checked: boolean) => {
      if (checked) {
        setSelectedRelations(
          relationList.map((rel: RelationItem) => rel.relation_key)
        );
      } else {
        setSelectedRelations([]);
      }
    };

    const handleRelationChange = (checkedValues: string[]) => {
      setSelectedRelations(checkedValues);
    };

    const handleExport = async () => {
      if (selectedAttrs.length === 0) {
        message.warning(t('Model.atLeastOneAttribute'));
        return;
      }

      setExporting(true);
      try {
        let instIds: any[] = [];

        switch (exportType) {
          case 'selected':
            instIds = selectedKeys;
            break;
          case 'currentPage':
            instIds = tableData.map((item) => item._id);
            break;
          case 'all':
            instIds = [];
            break;
        }

        const exportData = {
          inst_ids: instIds,
          attr_list: selectedAttrs,
          association_list: selectedRelations,
        };

        const response = await axios({
          url: `/api/proxy/cmdb/api/instance/${modelId}/inst_export/`,
          method: 'POST',
          responseType: 'blob',
          data: exportData,
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        const blob = new Blob([response.data], {
          type: response.headers['content-type'],
        });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `${modelId}${t('Model.assetList')}.xlsx`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        message.success(t('Model.exportSuccess'));
        setVisible(false);
      } catch (error: any) {
        console.error('Export failed:', error);
        message.error(error.message || t('Model.exportFailed'));
      } finally {
        setExporting(false);
      }
    };

    const handleCancel = () => {
      setVisible(false);
    };

    const isAttrIndeterminate =
      selectedAttrs.length > 0 &&
      selectedAttrs.length < availableColumns.length;
    const isAttrCheckAll = selectedAttrs.length === availableColumns.length;

    const isRelationIndeterminate =
      selectedRelations.length > 0 &&
      selectedRelations.length < relationList.length;
    const isRelationCheckAll = selectedRelations.length === relationList.length;

    return (
      <OperateModal
        title={title}
        visible={visible}
        onCancel={handleCancel}
        width={650}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              loading={exporting}
              onClick={handleExport}
              disabled={selectedAttrs.length === 0}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Spin spinning={loading}>
          <div
            style={{ maxHeight: '500px', overflowY: 'auto', padding: '8px' }}
          >
            <div className="mb-6">
              <div className="flex items-center justify-between mb-4">
                <div className="text-sm font-medium text-gray-700">
                  {t('Model.selectAttributes')}
                </div>
                <Checkbox
                  indeterminate={isAttrIndeterminate}
                  checked={isAttrCheckAll}
                  onChange={(e) => handleAttrSelectAll(e.target.checked)}
                  className="text-sm"
                >
                  {t('selectAll')}
                </Checkbox>
              </div>
              <div className="border border-gray-200 rounded-lg p-4 bg-gray-50 max-h-60 overflow-y-auto">
                <Checkbox.Group
                  value={selectedAttrs}
                  onChange={handleAttrChange}
                  className="w-full"
                >
                  <div className="grid grid-cols-3 gap-3 w-full">
                    {availableColumns.map((column) => (
                      <div
                        key={column.key}
                        className="flex items-center w-full min-w-0"
                      >
                        <Checkbox value={column.key} className="text-sm w-full">
                          <span className="text-sm text-gray-700 truncate block">
                            {column.title}
                          </span>
                        </Checkbox>
                      </div>
                    ))}
                  </div>
                </Checkbox.Group>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="text-sm font-medium text-gray-700">
                  {t('Model.selectAssociations')}
                </div>
                {relationList.length > 0 && (
                  <Checkbox
                    indeterminate={isRelationIndeterminate}
                    checked={isRelationCheckAll}
                    onChange={(e) => handleRelationSelectAll(e.target.checked)}
                    className="text-sm"
                  >
                    {t('selectAll')}
                  </Checkbox>
                )}
              </div>
              {relationList.length > 0 ? (
                <div className="border border-gray-200 rounded-lg p-4 bg-gray-50 max-h-48 overflow-y-auto">
                  <Checkbox.Group
                    value={selectedRelations}
                    onChange={handleRelationChange}
                    className="w-full"
                  >
                    <div className="space-y-3">
                      {relationList.map((relation: RelationItem) => (
                        <div
                          key={relation.relation_key}
                          className="flex items-center"
                        >
                          <Checkbox
                            value={relation.relation_key}
                            className="text-sm"
                          >
                            <span className="text-sm text-gray-700">
                              {relation.name}
                            </span>
                          </Checkbox>
                        </div>
                      ))}
                    </div>
                  </Checkbox.Group>
                </div>
              ) : (
                <div className="border border-gray-200 rounded-lg p-6 bg-gray-50">
                  <div className="text-sm text-gray-400 text-center">
                    {t('Model.noAssociations')}
                  </div>
                </div>
              )}
            </div>
          </div>
        </Spin>
      </OperateModal>
    );
  }
);

ExportModal.displayName = 'ExportModal';

export default ExportModal;
