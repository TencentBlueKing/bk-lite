'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Form,
  Input,
  Modal,
  Select,
  Switch,
  message,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import CustomTable from '@/components/custom-table';
import SearchActionBar from '@/components/search-action-bar';
import SourceOriginBadge from '@/components/source-origin-badge';
import PermissionWrapper from '@/components/permission';
import { useProcessFingerprintApi, type ProcessFingerprintItem } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import {
  FINGERPRINT_TARGET_TYPE_OPTIONS,
  getTargetTypeLabel,
} from '../fingerprintTargets';

const FEATURE_LIBRARY_PERMISSION_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/soid';

const ProcessFingerprintPage: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const typeFromUrl = (searchParams.get('type') || searchParams.get('target_type') || '').trim();

  const {
    getProcessFingerprintList,
    createProcessFingerprint,
    updateProcessFingerprint,
    deleteProcessFingerprint,
  } = useProcessFingerprintApi();

  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [dataList, setDataList] = useState<ProcessFingerprintItem[]>([]);
  const [selectedType, setSelectedType] = useState<string>(typeFromUrl);
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [modalLoading, setModalLoading] = useState<boolean>(false);
  const [form] = Form.useForm();

  const paginationRef = useRef(pagination);
  useEffect(() => {
    paginationRef.current = pagination;
  }, [pagination]);

  const fetchData = useCallback(
    async (params: { current?: number; pageSize?: number; type?: string; search?: string } = {}) => {
      try {
        setTableLoading(true);
        const curPage = params.current ?? paginationRef.current.current;
        const curPageSize = params.pageSize ?? paginationRef.current.pageSize;
        const curType = params.type !== undefined ? params.type : selectedType;
        const curSearch = params.search !== undefined ? params.search : searchKeyword;

        const queryParams: Record<string, unknown> = {
          page: curPage,
          page_size: curPageSize,
        };
        if (curType) {
          queryParams.target_type = curType;
        }
        if (curSearch) {
          queryParams.search = curSearch;
        }

        const data = await getProcessFingerprintList(queryParams);
        setDataList(data.items || []);
        setPagination((prev) => ({
          ...prev,
          total: data.count || 0,
          current: curPage,
          pageSize: curPageSize,
        }));
      } catch (error) {
        console.error(error);
        message.error(t('common.loadListFailed'));
      } finally {
        setTableLoading(false);
      }
    },
    [getProcessFingerprintList, selectedType, searchKeyword, t]
  );

  useEffect(() => {
    setSelectedType(typeFromUrl);
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ current: 1, type: typeFromUrl });
  }, [typeFromUrl]);

  const handleFilterChange = () => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ current: 1, type: selectedType, search: searchKeyword });
  };

  const handleResetFilter = () => {
    setSelectedType('');
    setSearchKeyword('');
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ current: 1, type: '', search: '' });
  };

  const handleToggleEnabled = useCallback(
    async (record: ProcessFingerprintItem, enabled: boolean) => {
      try {
        await updateProcessFingerprint(record.id, { enabled });
        message.success(t('OidLibrary.operateSuccess'));
        fetchData();
      } catch (err: any) {
        message.error(err?.message || t('OidLibrary.operateFailed'));
      }
    },
    [updateProcessFingerprint, fetchData, t]
  );

  const handleDelete = (record: ProcessFingerprintItem) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: async () => {
        try {
          await deleteProcessFingerprint(record.id);
          message.success(t('successfullyDeleted'));
          fetchData();
        } catch (err: any) {
          message.error(err?.message || t('OidLibrary.operateFailed'));
        }
      },
    });
  };

  const handleOpenAddModal = () => {
    form.resetFields();
    form.setFieldsValue({
      target_type: selectedType || undefined,
      linux_process: '',
      windows_image: '',
    });
    setModalOpen(true);
  };

  const handleAddSubmit = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);
      await createProcessFingerprint({
        target_type: values.target_type,
        linux_process: (values.linux_process || '').trim(),
        windows_image: (values.windows_image || '').trim(),
      });
      message.success(t('successfullyAdded'));
      setModalOpen(false);
      fetchData({ current: 1 });
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(err?.message || t('OidLibrary.operateFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const columns = useMemo(
    () => [
      {
        title: t('OidLibrary.targetType'),
        dataIndex: 'target_type',
        key: 'target_type',
        render: (type: string) => (
          <div className="flex items-center gap-2">
            <span className="font-medium text-[var(--color-text-1)]">{getTargetTypeLabel(type)}</span>
            <span className="font-mono text-xs text-[var(--color-text-3)]">({type})</span>
          </div>
        ),
      },
      {
        title: t('OidLibrary.linuxProcess'),
        dataIndex: 'linux_process',
        key: 'linux_process',
        render: (value: string) =>
          value ? (
            <span className="font-mono text-xs text-[var(--color-text-1)]">{value}</span>
          ) : (
            <span className="text-[var(--color-text-3)]">-</span>
          ),
      },
      {
        title: t('OidLibrary.windowsImage'),
        dataIndex: 'windows_image',
        key: 'windows_image',
        width: 180,
        render: (value: string) =>
          value ? (
            <span className="font-mono text-xs text-[var(--color-text-1)]">{value}</span>
          ) : (
            <span className="text-[var(--color-text-3)]">-</span>
          ),
      },
      {
        title: t('OidLibrary.builtIn'),
        dataIndex: 'built_in',
        key: 'built_in',
        width: 140,
        render: (builtIn: boolean) => (
          <SourceOriginBadge kind={builtIn ? 'builtin' : 'custom'} />
        ),
      },
      {
        title: t('OidLibrary.enabled'),
        dataIndex: 'enabled',
        key: 'enabled',
        width: 100,
        render: (_: boolean, record: ProcessFingerprintItem) => (
          <PermissionWrapper
            requiredPermissions={['Add']}
            permissionPath={FEATURE_LIBRARY_PERMISSION_PATH}
            instPermissions={record.permission}
          >
            <Switch
              size="small"
              checked={record.enabled}
              onChange={(checked) => handleToggleEnabled(record, checked)}
            />
          </PermissionWrapper>
        ),
      },
      {
        title: t('common.actions'),
        key: 'operation',
        width: 120,
        render: (_: unknown, record: ProcessFingerprintItem) => (
          <PermissionWrapper
            requiredPermissions={['Delete']}
            permissionPath={FEATURE_LIBRARY_PERMISSION_PATH}
            instPermissions={record.permission}
          >
            <Button
              type="link"
              size="small"
              danger
              disabled={record.built_in}
              onClick={() => handleDelete(record)}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        ),
      },
    ],
    [t, handleToggleEnabled]
  );

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0 px-4 pb-3 pt-4">
        <h2 className="m-0 text-base font-semibold text-[var(--color-text-1)]">
          {t('OidLibrary.processIntroTitle')}
        </h2>
        <p className="mb-0 mt-1 text-xs text-[var(--color-text-3)]">
          {t('OidLibrary.processIntroMessage')}
        </p>
      </div>

      <SearchActionBar
        filters={(
          <Select
            allowClear
            placeholder={t('OidLibrary.typePlaceholder')}
            value={selectedType || undefined}
            onChange={(val) => {
              setSelectedType(val || '');
            }}
            style={{ width: 200 }}
            options={FINGERPRINT_TARGET_TYPE_OPTIONS}
          />
        )}
        searchProps={{
          allowClear: true,
          placeholder: t('OidLibrary.processPlaceholder'),
          value: searchKeyword,
          onChange: (e) => setSearchKeyword(e.target.value),
          onSearch: handleFilterChange,
        }}
        actions={(
          <>
            {(selectedType || searchKeyword) && (
              <Button onClick={handleResetFilter}>{t('common.reset')}</Button>
            )}
            <PermissionWrapper
              requiredPermissions={['Add']}
              permissionPath={FEATURE_LIBRARY_PERMISSION_PATH}
            >
              <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenAddModal}>
                {t('common.new')}
              </Button>
            </PermissionWrapper>
          </>
        )}
      />

      <div className="min-h-0 h-full flex-1 overflow-hidden">
        <CustomTable
          size="middle"
          rowKey="id"
          loading={tableLoading}
          columns={columns}
          dataSource={dataList}
          pagination={pagination}
          onChange={(newPag) => {
            setPagination((prev) => ({
              ...prev,
              current: newPag.current || 1,
              pageSize: newPag.pageSize || 20,
            }));
            fetchData({
              current: newPag.current,
              pageSize: newPag.pageSize,
            });
          }}
        />
      </div>

      <Modal
        title={t('OidLibrary.addProcessFingerprint')}
        open={modalOpen}
        confirmLoading={modalLoading}
        onCancel={() => setModalOpen(false)}
        onOk={handleAddSubmit}
        destroyOnClose
      >
        <Form form={form} layout="vertical" className="pt-2">
          <Form.Item
            label={t('OidLibrary.targetType')}
            name="target_type"
            rules={[{ required: true, message: t('OidLibrary.typePlaceholder') }]}
          >
            <Select
              showSearch
              placeholder={t('OidLibrary.typePlaceholder')}
              options={FINGERPRINT_TARGET_TYPE_OPTIONS}
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase()) ||
                (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>

          <Form.Item
            label={t('OidLibrary.linuxProcess')}
            name="linux_process"
            extra={t('OidLibrary.linuxProcessHint')}
            dependencies={['windows_image']}
            rules={[
              {
                validator: async (_, value) => {
                  const linux = String(value || '').trim();
                  const windows = String(form.getFieldValue('windows_image') || '').trim();
                  if (!linux && !windows) {
                    throw new Error(t('OidLibrary.processRuleRequired'));
                  }
                },
              },
            ]}
          >
            <Input className="font-mono" placeholder={t('OidLibrary.linuxProcessPlaceholder')} />
          </Form.Item>

          <Form.Item
            label={t('OidLibrary.windowsImage')}
            name="windows_image"
            extra={t('OidLibrary.windowsImageHint')}
            dependencies={['linux_process']}
            rules={[
              {
                validator: async (_, value) => {
                  const windows = String(value || '').trim();
                  const linux = String(form.getFieldValue('linux_process') || '').trim();
                  if (!linux && !windows) {
                    throw new Error(t('OidLibrary.processRuleRequired'));
                  }
                },
              },
            ]}
          >
            <Input className="font-mono" placeholder={t('OidLibrary.windowsImagePlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ProcessFingerprintPage;
