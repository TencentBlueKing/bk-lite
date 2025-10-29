'use client';
import React, { useEffect, useState } from 'react';
import { Input, Button, Popconfirm, message, TablePaginationConfig } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import TopSection from '@/components/top-section';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';
import QuotaModal from './quotaModal';
import { useQuotaApi } from '@/app/opspilot/api/settings';
import { ColumnsType } from 'antd/es/table';

const { Search } = Input;

interface QuotaRecord {
  id: number;
  name: string;
  target_type: string;
  target_list: string[];
  rule_type: string;
  file_size: number;
  unit: string;
  skill_count: number;
  bot_count: number;
}

interface QuotaParams {
  page?: number;
  pageSize?: number;
  name?: string;
}

const QuotaManagementPage: React.FC = () => {
  const { t } = useTranslation();
  const { fetchQuotaRules, deleteQuotaRule, saveQuotaRule } = useQuotaApi();
  const [data, setData] = useState<QuotaRecord[]>([]);
  const [pagination, setPagination] = useState<TablePaginationConfig>({ current: 1, pageSize: 10, total: 0 });
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalMode, setModalMode] = useState<'add' | 'edit'>('add');
  const [currentRecord, setCurrentRecord] = useState<QuotaRecord | null>(null);
  const [searchKey, setSearchKey] = useState('');

  const fetchData = async (params: QuotaParams = {}) => {
    setLoading(true);
    try {
      const result = await fetchQuotaRules({ ...params, page_size: pagination.pageSize });
      setData(result.items);
      setPagination((prev) => ({ ...prev, total: result.count, current: params.page || 1 }));
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData({ page: pagination.current });
  }, [pagination.current]);

  const handleTableChange = (page: number | undefined, pageSize: number | undefined) => {
    setPagination((prev) => ({
      ...prev,
      current: page,
      pageSize: pageSize,
    }));
    fetchData({ page, pageSize, name: searchKey });
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteQuotaRule(id);
      message.success(t('common.delSuccess'));
      fetchData({ page: pagination.current }); // Refresh the data after delete
    } catch (error) {
      console.error(`${t('common.delFailed')}:`, error);
    }
  };

  const showModal = (mode: 'add' | 'edit', record: QuotaRecord | null = null) => {
    let formattedRecord: any = null;
    if (record) {
      formattedRecord = {
        ...record,
        targetType: record.target_type,
        targetList: record.target_list,
        rule: record.rule_type,
        file_size: record.file_size.toString(), // Ensure the value is a string if it needs to be
        unit: record.unit,
        skills: record.skill_count.toString(),
        bots: record.bot_count.toString(),
      };
    }
    setModalMode(mode);
    setCurrentRecord(formattedRecord);
    setModalVisible(true);
  };

  const handleCancel = () => {
    setModalVisible(false);
    setCurrentRecord(null);
  };

  const handleConfirm = async (values: any) => {
    const { name, targetType, targetList, rule, file_size, unit, skills, bots } = values;
    const payload = {
      name,
      target_type: targetType,
      target_list: targetList,
      rule_type: rule,
      file_size: parseInt(file_size, 10),
      unit,
      skill_count: parseInt(skills, 10),
      bot_count: parseInt(bots, 10),
    };

    try {
      await saveQuotaRule(modalMode, currentRecord?.id, payload);
      fetchData({ page: pagination.current });
      setModalVisible(false);
    } catch (error) {
      console.error('Failed to save quota:', error);
    }
  };

  const handleSearch = (value: string) => {
    setSearchKey(value);
    fetchData({ page: 1, name: value });
  };

  const columns: ColumnsType<QuotaRecord> = [
    {
      title: t('settings.manageQuota.name'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('settings.manageQuota.knowledgeBase'),
      dataIndex: 'knowledgeBase',
      key: 'knowledgeBase',
      render: (text, record) => `${record.file_size} ${record.unit}`,
    },
    {
      title: t('settings.manageQuota.skill'),
      dataIndex: 'skill',
      key: 'skill',
      render: (text, record) => record.skill_count,
    },
    {
      title: t('settings.manageQuota.bot'),
      dataIndex: 'bot',
      key: 'bot',
      render: (text, record) => record.bot_count,
    },
    {
      title: t('common.actions'),
      render: (text, record) => (
        <>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button type="link" className="mr-[8px]" onClick={() => showModal('edit', record)}>{t('common.edit')}</Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('common.delConfirm')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => handleDelete(record.id)}>
              <Button type="link" danger>{t('common.delete')}</Button>
            </Popconfirm>
          </PermissionWrapper>
        </>
      ),
    },
  ];

  return (
    <>
      <div className="h-full w-full">
        <div className="mb-4">
          <TopSection
            title={t('settings.manageQuota.title')}
            content={t('settings.manageQuota.content')}
          />
        </div>
        <div className="p-4 rounded-md bg-[var(--color-bg)]">
          <div className="flex justify-end mb-4">
            <Search
              placeholder={`${t('common.search')}...`}
              onSearch={handleSearch}
              enterButton={<SearchOutlined />}
              className="mr-2 w-60"
              onChange={(e) => setSearchKey(e.target.value)}
            />
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button type="primary" onClick={() => showModal('add')}>+ {t('common.add')}</Button>
            </PermissionWrapper>
          </div>
          <CustomTable
            scroll={{ y: 'calc(100vh - 425px)' }}
            dataSource={data}
            columns={columns}
            pagination={{
              pageSize: pagination.pageSize,
              current: pagination.current,
              total: pagination.total,
              onChange: handleTableChange,
            }}
            loading={loading}
            rowKey={(record) => record.id}
          />
        </div>
      </div>

      <QuotaModal
        visible={modalVisible}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
        mode={modalMode}
        initialValues={currentRecord}
        key={`${modalMode}-${currentRecord ? currentRecord.id : 'new'}`}
      />
    </>
  );
};

export default QuotaManagementPage;
