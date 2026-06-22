'use client';
import React, { useEffect, useState } from 'react';
import { Drawer, Select, Input, Table, Button, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import { filterNetworkDeviceModels, INTERFACE_MODEL } from './topoEditingUtils';

export interface AddableDevice {
  id: string;
  name: string;
  model_id: string;
}

interface AddDevicePanelProps {
  open: boolean;
  onClose: () => void;
  existingIds: Set<string>;
  modelNameOf: (modelId: string) => string;
  onAdd: (devices: AddableDevice[]) => void;
}

const AddDevicePanel: React.FC<AddDevicePanelProps> = ({
  open,
  onClose,
  existingIds,
  modelNameOf,
  onAdd,
}) => {
  const { t } = useTranslation();
  const { searchInstances } = useInstanceApi();
  const { getModelAssociations } = useModelApi();

  const [networkModels, setNetworkModels] = useState<string[]>([]);
  const [modelId, setModelId] = useState<string>();
  const [keyword, setKeyword] = useState('');
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  // 仅在打开时取一次：getModelAssociations 每次渲染都是新引用，
  // 若入依赖会在面板打开期间无限请求后端。
  useEffect(() => {
    if (!open) return;
    getModelAssociations(INTERFACE_MODEL)
      .then((assoc: any[]) => setNetworkModels(filterNetworkDeviceModels(assoc)))
      .catch(() => setNetworkModels([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const search = async (mid: string) => {
    setLoading(true);
    try {
      const params = {
        model_id: mid,
        query_list: keyword
          ? [{ field: 'inst_name', type: 'str*', value: keyword }]
          : [],
        page: 1,
        page_size: 50,
        order: '',
        role: '',
      };
      const data = await searchInstances(params);
      setRows(data.insts || []);
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = () => {
    const picked = rows
      .filter((r) => selected.includes(String(r._id)))
      .map((r) => ({
        id: String(r._id),
        name: r.inst_name,
        model_id: modelId as string,
      }));
    if (!picked.length) {
      message.warning(t('Model.networkTopoPickDevice'));
      return;
    }
    onAdd(picked);
    setSelected([]);
    onClose();
  };

  return (
    <Drawer
      title={t('Model.networkTopoAddDevice')}
      open={open}
      onClose={onClose}
      width={520}
    >
      <div className="flex gap-2 mb-3">
        <Select
          className="w-[200px]"
          placeholder={t('Model.networkTopoSelectModel')}
          value={modelId}
          onChange={(v) => {
            setModelId(v);
            setSelected([]);
            search(v);
          }}
          options={networkModels.map((m) => ({
            label: modelNameOf(m),
            value: m,
          }))}
        />
        <Input.Search
          placeholder={t('common.search')}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onSearch={() => modelId && search(modelId)}
          allowClear
        />
      </div>
      <Table
        size="small"
        loading={loading}
        rowKey={(r) => String(r._id)}
        dataSource={rows}
        pagination={false}
        scroll={{ y: 'calc(100vh - 260px)' }}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as string[]),
          getCheckboxProps: (r: any) => ({
            disabled: existingIds.has(String(r._id)),
          }),
        }}
        columns={[
          { title: t('Model.networkTopoDeviceName'), dataIndex: 'inst_name' },
          {
            title: t('Model.networkTopoStatusCol'),
            render: (_: unknown, r: any) =>
              existingIds.has(String(r._id))
                ? t('Model.networkTopoOnCanvas')
                : '',
          },
        ]}
      />
      <div className="mt-3 text-right">
        <Button type="primary" onClick={handleAdd}>
          {t('Model.networkTopoAddToCanvas')}
        </Button>
      </div>
    </Drawer>
  );
};

export default AddDevicePanel;
