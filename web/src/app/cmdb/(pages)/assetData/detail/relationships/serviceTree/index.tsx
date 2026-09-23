'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Dropdown,
  Input,
  Modal,
  Pagination,
  Select,
  Space,
  Table,
  Tree,
  message,
} from 'antd';
import type { MenuProps } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api';
import PermissionWrapper from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import usePermissions from '@/hooks/usePermissions';
import { RACK_ROOM_ASSET_PERMISSION_PATH } from '../rackRoomEdit';
import {
  ASSIGN_HOST_PAGE_SIZE,
  canAssignHosts,
  canCreateApplication,
  collectTreeKeys,
  createLayerActions,
  hostCandidateQuery,
  hostsForAction,
  mergePageSelection,
  toAntdTree,
  transferAppLabel,
  type ServiceTreeKind,
  type ServiceTreeNode,
} from './treeModel';

interface ServiceTreeProps {
  instUuid: string;
}

interface HostRow {
  inst_uuid: string;
  inst_name: string;
  ip_addr?: string;
  applications?: { inst_uuid: string; inst_name: string }[];
}

interface AppOption {
  inst_uuid: string;
  inst_name: string;
  system_name?: string;
}

const ServiceTree: React.FC<ServiceTreeProps> = ({ instUuid }) => {
  const { t } = useTranslation();
  const api = useInstanceApi();
  const { hasPermission } = usePermissions(RACK_ROOM_ASSET_PERMISSION_PATH);
  const [tree, setTree] = useState<ServiceTreeNode | null>(null);
  const [selectedKey, setSelectedKey] = useState(instUuid);
  const [hosts, setHosts] = useState<HostRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [hostLoading, setHostLoading] = useState(false);
  const detailRequestRef = useRef(0);
  const [nameModal, setNameModal] = useState<{ kind: string; mode: 'create' | 'rename'; modelName?: string } | null>(null);
  const [nodeName, setNodeName] = useState('');
  const [assignOpen, setAssignOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [hostKeyword, setHostKeyword] = useState('');
  const [hostCandidates, setHostCandidates] = useState<HostRow[]>([]);
  const [assignPage, setAssignPage] = useState(1);
  const [assignTotal, setAssignTotal] = useState(0);
  const [assignLoading, setAssignLoading] = useState(false);
  const [appCandidates, setAppCandidates] = useState<AppOption[]>([]);
  const [selectedHosts, setSelectedHosts] = useState<string[]>([]);
  const [assignHostKeys, setAssignHostKeys] = useState<string[]>([]);
  const [assignSubmitting, setAssignSubmitting] = useState(false);
  const [targetApp, setTargetApp] = useState('');
  const [transferSubmitting, setTransferSubmitting] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const selected = useMemo(() => findNode(tree, selectedKey), [tree, selectedKey]);

  const loadTree = async (selectUuid = selectedKey) => {
    setLoading(true);
    setHosts([]);
    setSelectedHosts([]);
    try {
      const data = await api.getServiceTree(instUuid);
      setTree(data);
      setExpandedKeys(collectTreeKeys(data));
      const next = findNode(data, selectUuid) ? selectUuid : data.inst_uuid;
      setSelectedKey(next);
      await loadDetail(next);
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (nodeUuid: string) => {
    const requestId = detailRequestRef.current + 1;
    detailRequestRef.current = requestId;
    setHosts([]);
    setSelectedHosts([]);
    setHostLoading(true);
    try {
      const data = await api.getServiceTreeHosts(instUuid, nodeUuid);
      if (requestId !== detailRequestRef.current) return;
      setHosts(data.hosts || []);
    } finally {
      if (requestId === detailRequestRef.current) {
        setHostLoading(false);
      }
    }
  };

  useEffect(() => {
    loadTree(instUuid);
  }, [instUuid]);

  const currentKind: ServiceTreeKind = selected?.kind || 'system';
  const assignable = canAssignHosts(currentKind);
  const layerActions = createLayerActions(selected);
  const canCreateApp = canCreateApplication(selected);

  const kindLabel = (kind: ServiceTreeKind, modelName?: string) => {
    if (kind === 'system') return t('Model.serviceTreeKindSystem');
    if (kind === 'application') return t('Model.serviceTreeKindApp');
    return modelName || kind;
  };

  const submitName = async () => {
    if (!nameModal || !nodeName.trim() || !selected) return;
    if (nameModal.mode === 'rename') {
      await api.renameServiceTreeNode(instUuid, {
        node_uuid: selected.inst_uuid,
        inst_name: nodeName.trim(),
      });
      message.success(t('successfullyModified'));
    } else {
      await api.createServiceTreeChild(instUuid, {
        parent_uuid: selected.inst_uuid,
        kind: nameModal.kind,
        inst_name: nodeName.trim(),
      });
      message.success(t('successfullyAdded'));
    }
    setNameModal(null);
    setNodeName('');
    await loadTree(selected.inst_uuid);
  };

  const removeSelected = () => {
    if (!selected || selected.kind === 'system') return;
    Modal.confirm({
      title: t('common.delete'),
      onOk: async () => {
        await api.deleteServiceTreeNode(instUuid, selected.inst_uuid);
        message.success(t('successfullyDeleted'));
        await loadTree(instUuid);
      },
    });
  };

  const searchApps = async (keyword = '') => {
    const data = await api.searchInstances({
      model_id: 'application',
      query_list: keyword
        ? [{ field: 'inst_name', type: 'str*', value: keyword }]
        : [],
      page: 1,
      page_size: 50,
      order: '',
      role: '',
    });
    const insts = ((data.insts || []) as AppOption[]).filter((item) => item.inst_uuid !== selectedKey);
    const mapping = insts.length
      ? await api.getServiceTreeApplicationSystems(
        instUuid,
        insts.map((item) => item.inst_uuid),
      )
      : {};
    setAppCandidates(
      insts.map((item) => ({
        ...item,
        system_name: mapping?.[item.inst_uuid]?.inst_name || '',
      })),
    );
  };

  const selectedHostRows = useMemo(
    () => hostsForAction(hosts, selectedHosts),
    [hosts, selectedHosts],
  );

  const searchHosts = async (page = 1, keyword = hostKeyword) => {
    setAssignLoading(true);
    try {
      const data = await api.searchInstances({
        model_id: 'host',
        query_list: hostCandidateQuery(keyword),
        page,
        page_size: ASSIGN_HOST_PAGE_SIZE,
        order: '',
        role: '',
      });
      setHostCandidates(data.insts || []);
      setAssignTotal(data.count || 0);
      setAssignPage(page);
    } finally {
      setAssignLoading(false);
    }
  };

  const refreshAfterHostChange = async () => {
    setHostLoading(true);
    try {
      const [treeData, hostData] = await Promise.all([
        api.getServiceTree(instUuid),
        api.getServiceTreeHosts(instUuid, selectedKey),
      ]);
      setTree(treeData);
      setHosts(hostData.hosts || []);
      setSelectedHosts([]);
    } finally {
      setHostLoading(false);
    }
  };

  const runAssign = async () => {
    if (assignSubmitting) return Promise.reject();
    if (!assignHostKeys.length) {
      message.warning(t('Model.serviceTreePickHost'));
      return Promise.reject();
    }
    setAssignSubmitting(true);
    try {
      await api.assignServiceTreeHosts(instUuid, {
        application_uuid: selectedKey,
        host_uuids: assignHostKeys,
      });
      setAssignOpen(false);
      setAssignHostKeys([]);
      message.success(t('successfullyAdded'));
      void refreshAfterHostChange();
    } finally {
      setAssignSubmitting(false);
    }
  };

  const runTransfer = async () => {
    if (transferSubmitting) return Promise.reject();
    if (!selectedHostRows.length || !targetApp) {
      message.warning(t('Model.serviceTreePickHost'));
      return Promise.reject();
    }
    setTransferSubmitting(true);
    try {
      await api.transferServiceTreeHosts(instUuid, {
        source_app: selectedKey,
        target_app: targetApp,
        host_uuids: selectedHostRows.map((item) => item.inst_uuid),
      });
      setTransferOpen(false);
      setSelectedHosts([]);
      setTargetApp('');
      message.success(t('successfullyAdded'));
      void refreshAfterHostChange();
    } finally {
      setTransferSubmitting(false);
    }
  };

  const runUnbind = () => {
    if (!selectedHostRows.length) {
      message.warning(t('Model.serviceTreePickHost'));
      return;
    }
    Modal.confirm({
      title: t('Model.serviceTreeUnbind'),
      content: t('Model.serviceTreeUnbindConfirm', '将从当前应用解除 {count} 台主机的挂靠。主机资产保留，其它应用上的挂靠不变。', {
        count: selectedHostRows.length,
      }),
      onOk: async () => {
        await api.unbindServiceTreeHosts(instUuid, {
          application_uuid: selectedKey,
          host_uuids: selectedHostRows.map((item) => item.inst_uuid),
        });
        setSelectedHosts([]);
        message.success(t('successfullyDeleted'));
        void refreshAfterHostChange();
      },
    });
  };

  const exportTree = async () => {
    const blob = await api.exportServiceTree(instUuid);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'service_tree.xlsx';
    link.click();
    URL.revokeObjectURL(url);
  };

  const openAssign = () => {
    setAssignHostKeys([]);
    setHostKeyword('');
    setAssignPage(1);
    setAssignOpen(true);
    void searchHosts(1, '');
  };

  const openTransfer = () => {
    if (!selectedHostRows.length) {
      message.warning(t('Model.serviceTreePickHost'));
      return;
    }
    setTransferOpen(true);
    searchApps();
  };

  const hostActionItems: MenuProps['items'] = [
    {
      key: 'assign',
      label: t('Model.serviceTreeAssign'),
      onClick: openAssign,
    },
    {
      key: 'transfer',
      label: t('Model.serviceTreeTransfer'),
      onClick: openTransfer,
    },
    {
      key: 'unbind',
      label: t('Model.serviceTreeUnbind'),
      danger: true,
      onClick: runUnbind,
    },
  ];

  const moreItems: MenuProps['items'] = [
    ...(hasPermission(['Add'])
      ? [
        {
          key: 'import',
          label: t('Model.serviceTreeImport'),
          onClick: () => fileRef.current?.click(),
        },
      ]
      : []),
    {
      key: 'export',
      label: t('Model.serviceTreeExport'),
      onClick: () => {
        void exportTree();
      },
    },
  ];

  const treeData: DataNode[] = tree ? [toAntdTree(tree)] : [];

  return (
    <div className="flex h-full min-h-0 overflow-hidden rounded border border-[var(--color-border)]">
      <aside className="flex w-[280px] shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-fill-1)]">
        <div className="border-b border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-3">
          <div className="text-lg font-semibold leading-7">{t('Model.serviceTree')}</div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto py-2">
          <Tree
            blockNode
            className="text-[15px] [&_.ant-tree-treenode]:w-full [&_.ant-tree-node-content-wrapper]:min-w-0 [&_.ant-tree-node-content-wrapper]:flex-1 [&_.ant-tree-node-content-wrapper]:overflow-hidden [&_.ant-tree-title]:block [&_.ant-tree-title]:min-w-0 [&_.ant-tree-title]:overflow-hidden"
            selectedKeys={[selectedKey]}
            expandedKeys={expandedKeys}
            onExpand={(keys) => setExpandedKeys(keys.map(String))}
            treeData={treeData}
            titleRender={(node: any) => (
              <span className="flex w-full min-w-0 items-center gap-2 text-[15px] leading-5">
                <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${
                    node.kind === 'system'
                      ? 'bg-[var(--color-primary)]'
                      : node.kind === 'application'
                        ? 'bg-[var(--color-warning)]'
                        : 'bg-[var(--color-success)]'
                  }`} />
                <EllipsisWithTooltip
                  className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-[15px] leading-5"
                  text={String(node.title || '')}
                  getPopupContainer={() => document.body}
                />
                <span className="ml-auto shrink-0 text-xs text-[var(--color-text-3)]">{node.host_count}</span>
              </span>
            )}
            onSelect={(keys) => {
              if (!keys.length) return;
              const key = String(keys[0]);
              if (key === selectedKey && !hostLoading) return;
              setSelectedKey(key);
              void loadDetail(key);
            }}
          />
        </div>
      </aside>
      <section className="flex min-w-0 flex-1 flex-col bg-[var(--color-bg)]">
        <div className="flex items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
          <div>
            <h2 className="m-0 text-base font-semibold">{selected?.inst_name || '-'}</h2>
            <div className="text-xs text-[var(--color-text-3)]">
              {kindLabel(currentKind, selected?.model_name)}
            </div>
          </div>
          <Space wrap>
            <PermissionWrapper requiredPermissions={['Add']} permissionPath={RACK_ROOM_ASSET_PERMISSION_PATH}>
              {layerActions.map((layer) => (
                <Button
                  key={layer.model_id}
                  onClick={() => setNameModal({ kind: layer.model_id, mode: 'create', modelName: layer.model_name })}
                >
                  {t('Model.serviceTreeNewModel', '新建{name}', { name: layer.model_name })}
                </Button>
              ))}
              {canCreateApp && (
                <Button onClick={() => setNameModal({ kind: 'application', mode: 'create' })}>{t('Model.serviceTreeNewApp')}</Button>
              )}
            </PermissionWrapper>
            {currentKind !== 'system' && (
              <>
                <PermissionWrapper requiredPermissions={['Edit']} permissionPath={RACK_ROOM_ASSET_PERMISSION_PATH}>
                  <Button
                    onClick={() => {
                      setNameModal({
                        kind: currentKind,
                        mode: 'rename',
                        modelName: selected?.model_name,
                      });
                      setNodeName(selected?.inst_name || '');
                    }}
                  >
                    {t('common.edit')}
                  </Button>
                </PermissionWrapper>
                <PermissionWrapper requiredPermissions={['Delete']} permissionPath={RACK_ROOM_ASSET_PERMISSION_PATH}>
                  <Button danger onClick={removeSelected}>{t('common.delete')}</Button>
                </PermissionWrapper>
              </>
            )}
            {assignable && (
              <PermissionWrapper requiredPermissions={['Edit']} permissionPath={RACK_ROOM_ASSET_PERMISSION_PATH}>
                <Dropdown
                  trigger={['hover']}
                  mouseEnterDelay={0.1}
                  mouseLeaveDelay={0.15}
                  menu={{ items: hostActionItems }}
                >
                  <Button>
                    <Space>
                      {t('Model.serviceTreeHostActions')}
                      <DownOutlined />
                    </Space>
                  </Button>
                </Dropdown>
              </PermissionWrapper>
            )}
            <Dropdown menu={{ items: moreItems }} placement="bottomRight">
              <Button>
                <Space>
                  {t('common.more')}
                  <DownOutlined />
                </Space>
              </Button>
            </Dropdown>
          </Space>
        </div>
        <p className="m-0 border-b border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-2 text-[var(--color-text-2)]">
          {assignable ? t('Model.serviceTreeHintApp') : t('Model.serviceTreeHintSystem')}
        </p>
        <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
          <div className="mb-2 font-medium">{t('Model.serviceTreeHosts')}</div>
          <div className="min-h-[240px]">
            <Table
              rowKey="inst_uuid"
              size="small"
              loading={{ spinning: hostLoading || loading, tip: t('common.loading') }}
              pagination={{ pageSize: 50, showSizeChanger: false }}
              rowSelection={assignable ? { selectedRowKeys: selectedHosts, onChange: (keys) => setSelectedHosts(keys.map(String)) } : undefined}
              dataSource={hosts}
              columns={[
                { title: t('Model.serviceTreeName'), dataIndex: 'inst_name' },
                { title: 'IP', dataIndex: 'ip_addr' },
                {
                  title: t('Model.serviceTreeHostApps'),
                  dataIndex: 'applications',
                  render: (apps: HostRow['applications']) => (apps || []).map((item) => item.inst_name).join(' / '),
                },
              ]}
              locale={{ emptyText: hostLoading || loading ? ' ' : t('Model.serviceTreeEmptyHosts') }}
            />
          </div>
        </div>
      </section>
      <input
        ref={fileRef}
        type="file"
        accept=".xlsx,.csv"
        className="hidden"
        onChange={async (event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (!file) return;
          const form = new FormData();
          form.append('file', file);
          const result = await api.importServiceTree(instUuid, form);
          if (result?.errors?.length) {
            message.warning(`${result.errors[0].message} (${result.errors.length})`);
          } else {
            message.success(t('Model.importSuccess'));
          }
          await loadTree(selectedKey);
        }}
      />
      <Modal
        title={
          nameModal?.mode === 'rename'
            ? t('common.edit')
            : nameModal?.kind === 'application'
              ? t('Model.serviceTreeNewApp')
              : t('Model.serviceTreeNewModel', '新建{name}', { name: nameModal?.modelName || '' })
        }
        open={Boolean(nameModal)}
        onCancel={() => setNameModal(null)}
        onOk={submitName}
      >
        <Input value={nodeName} onChange={(event) => setNodeName(event.target.value)} placeholder={t('Model.serviceTreeName')} />
      </Modal>
      <Modal
        title={t('Model.serviceTreeAssign')}
        open={assignOpen}
        confirmLoading={assignSubmitting}
        maskClosable={!assignSubmitting}
        keyboard={!assignSubmitting}
        onCancel={() => {
          if (!assignSubmitting) setAssignOpen(false);
        }}
        onOk={runAssign}
        width={720}
        classNames={{ body: 'flex h-[520px] flex-col overflow-hidden' }}
      >
        <Input.Search
          className="mb-3"
          value={hostKeyword}
          allowClear
          placeholder={t('Model.serviceTreeSearchHost')}
          onChange={(event) => setHostKeyword(event.target.value)}
          onSearch={(value) => {
            setHostKeyword(value);
            void searchHosts(1, value);
          }}
        />
        <div className="mb-2 text-xs text-[var(--color-text-3)]">
          {t('Model.serviceTreeSelectedCount', '已选 {count} 台', { count: assignHostKeys.length })}
        </div>
        <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
          <Table
            rowKey="inst_uuid"
            size="small"
            loading={assignLoading}
            pagination={false}
            scroll={{ y: 320 }}
            rowSelection={{
              selectedRowKeys: assignHostKeys,
              preserveSelectedRowKeys: true,
              onChange: (keys) =>
                setAssignHostKeys(
                  mergePageSelection(
                    assignHostKeys,
                    hostCandidates.map((item) => item.inst_uuid),
                    keys.map(String),
                  ),
                ),
            }}
            dataSource={hostCandidates}
            columns={[
              { title: t('Model.serviceTreeName'), dataIndex: 'inst_name' },
              { title: 'IP', dataIndex: 'ip_addr' },
            ]}
          />
        </div>
        <div className="mt-2 flex justify-end">
          <Pagination
            size="small"
            current={assignPage}
            pageSize={ASSIGN_HOST_PAGE_SIZE}
            total={assignTotal}
            showSizeChanger={false}
            onChange={(page) => {
              void searchHosts(page);
            }}
          />
        </div>
      </Modal>
      <Modal
        title={t('Model.serviceTreeTransfer')}
        open={transferOpen}
        confirmLoading={transferSubmitting}
        maskClosable={!transferSubmitting}
        keyboard={!transferSubmitting}
        onCancel={() => {
          if (!transferSubmitting) setTransferOpen(false);
        }}
        onOk={runTransfer}
      >
        <div className="mb-3 text-[var(--color-text-2)]">
          {t('Model.serviceTreeTransferHosts', '将转移 {count} 台主机', { count: selectedHostRows.length })}
          ：{selectedHostRows.map((item) => item.inst_name).join('、')}
        </div>
        <div className="mb-3 text-[var(--color-text-2)]">{t('Model.serviceTreeTargetApp')}</div>
        <Select
          showSearch
          className="w-full"
          value={targetApp || undefined}
          placeholder={t('Model.serviceTreeTargetApp')}
          filterOption={false}
          onSearch={searchApps}
          onChange={(value) => setTargetApp(String(value || ''))}
          options={appCandidates.map((item) => ({
            value: item.inst_uuid,
            label: transferAppLabel(item),
          }))}
        />
      </Modal>
    </div>
  );
};

function findNode(node: ServiceTreeNode | null, uuid: string): ServiceTreeNode | null {
  if (!node) return null;
  if (node.inst_uuid === uuid) return node;
  for (const child of node.children || []) {
    const found = findNode(child, uuid);
    if (found) return found;
  }
  return null;
}

export default ServiceTree;
