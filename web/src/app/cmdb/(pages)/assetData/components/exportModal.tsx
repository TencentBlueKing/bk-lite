'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import axios from 'axios';
import OperateModal from '@/components/operate-modal';
import { Checkbox, Button, Spin, message } from 'antd';
import { HolderOutlined } from '@ant-design/icons';
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
    const [dragIndex, setDragIndex] = useState<number | null>(null);
    const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

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

        // 获取表头显示的字段（如果有传displayFieldKeys）
        const displayFieldKeys =
          (config as any).displayFieldKeys ||
          filteredColumns.map((col) => col.key as string);

        // 按照表头顺序排列：已勾选的在前，未勾选的在后
        const displayedCols = displayFieldKeys
          .map((key: string) => filteredColumns.find((col) => col.key === key))
          .filter(Boolean) as ColumnItem[];

        const unDisplayedCols = filteredColumns.filter(
          (col) => !displayFieldKeys.includes(col.key as string)
        );

        const orderedColumns = [...displayedCols, ...unDisplayedCols];

        setAvailableColumns(orderedColumns);

        // 默认只选中表头已勾选的字段
        setSelectedAttrs(displayFieldKeys);

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

    const handleDragStart = (index: number) => {
      setDragIndex(index);
    };

    const handleDragOver = (e: React.DragEvent, index: number) => {
      e.preventDefault();
      if (dragIndex !== null && dragIndex !== index) {
        setDragOverIndex(index);
      }
    };

    const handleDragEnd = () => {
      if (
        dragIndex !== null &&
        dragOverIndex !== null &&
        dragIndex !== dragOverIndex
      ) {
        const newColumns = [...availableColumns];
        const draggedItem = newColumns[dragIndex];
        newColumns.splice(dragIndex, 1);
        newColumns.splice(dragOverIndex, 0, draggedItem);
        setAvailableColumns(newColumns);
      }
      setDragIndex(null);
      setDragOverIndex(null);
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

        // 按照拖拽后的顺序
        const orderedAttrs = availableColumns
          .filter((col) => selectedAttrs.includes(col.key as string))
          .map((col) => col.key as string);

        const exportData = {
          inst_ids: instIds,
          attr_list: orderedAttrs,
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
                    {availableColumns.map((column, index) => (
                      <div
                        key={column.key}
                        className="flex items-center w-full min-w-0 cursor-move transition-all"
                        draggable
                        onDragStart={() => handleDragStart(index)}
                        onDragOver={(e) => handleDragOver(e, index)}
                        onDragEnd={handleDragEnd}
                        style={{
                          opacity: dragIndex === index ? 0.4 : 1,
                          transform:
                            dragOverIndex === index && dragIndex !== index
                              ? 'scale(1.02)'
                              : 'scale(1)',
                          backgroundColor:
                            dragOverIndex === index && dragIndex !== index
                              ? '#e6f7ff'
                              : 'transparent',
                          borderRadius: '4px',
                          padding: '2px',
                        }}
                      >
                        <HolderOutlined
                          className="mr-1 text-gray-400"
                          style={{ fontSize: '12px', cursor: 'grab' }}
                        />
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
                    <div className="flex flex-col gap-3">
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
