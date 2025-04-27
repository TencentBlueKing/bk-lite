'use client';
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Input, Spin, Button, Pagination, Switch, message, Popconfirm } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import ModifyRuleModal from './modifyRuleModal';
import PermissionWrapper from '@/components/permission';
import { useSkillApi } from '@/app/opspilot/api/skill';

const { Search } = Input;

interface SkillRule {
  key: string;
  name: string;
  created_at: string;
  created_by: string;
  is_enabled: boolean;
  [key: string]: any;
}

const SkillRules: React.FC = () => {
  const { t } = useTranslation();
  const { fetchRules, updateRule, deleteRule } = useSkillApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [searchText, setSearchText] = useState('');
  const [data, setData] = useState<SkillRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [selectedSkillRule, setSelectedSkillRule] = useState<SkillRule | null>(null);
  const [total, setTotal] = useState(0);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
  });
  const [switchLoading, setSwitchLoading] = useState<{ [key: string]: boolean }>({});

  const fetchSkillRules = useCallback(async (searchText = '', page = 1, pageSize = 10) => {
    setLoading(true);
    try {
      const params: any = { page, page_size: pageSize };
      if (searchText) params.name = searchText;

      const res = await fetchRules(params);
      setData(res.items);
      setTotal(res.count);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchSkillRules();
  }, []);

  const handleSearch = (value: string) => {
    setSearchText(value);
    setPagination({ ...pagination, current: 1 });
    fetchSkillRules(value, 1, pagination.pageSize);
  };

  const handleTableChange = (page: number, pageSize?: number) => {
    const newPagination = {
      current: page,
      pageSize: pageSize || pagination.pageSize,
    };
    setPagination(newPagination);
    fetchSkillRules(searchText, newPagination.current, newPagination.pageSize);
  };

  const handlePageSizeChange = (current: number, size: number) => {
    handleTableChange(current, size);
  };

  const handleSwitchChange = async (checked: boolean, record: SkillRule) => {
    const { id } = record;
    setSwitchLoading((prev) => ({ ...prev, [id]: true }));
    try {
      await updateRule(id, { is_enabled: checked });
      fetchSkillRules(searchText, pagination.current, pagination.pageSize);
    } catch (error) {
      console.error(`${t('common.updateFailed')}:`, error);
    } finally {
      setSwitchLoading((prev) => ({ ...prev, [id]: false }));
    }
  };

  const openModal = (skillRule: SkillRule | null = null) => {
    setSelectedSkillRule(skillRule);
    setModalVisible(true);
  };

  const handleAdd = () => openModal();

  const handleEdit = (record: SkillRule) => openModal(record);

  const handleConfirmRule = () => {
    setModalVisible(false);
    fetchSkillRules();
    setSelectedSkillRule(null);
  };

  const handleDeleteRule = async (id: number) => {
    try {
      await deleteRule(id);
      fetchSkillRules();
      message.success(t('common.delSuccess'));
    } catch (error) {
      console.error(`${t('common.delFailed')}:`, error);
    } finally {
      setSelectedSkillRule(null);
    }
  };

  const columns = [
    {
      title: t('skill.rules.table.name'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('skill.rules.table.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (text: string) => convertToLocalizedTime(text),
    },
    {
      title: t('skill.rules.table.creator'),
      dataIndex: 'created_by',
      key: 'created_by',
    },
    {
      title: t('skill.rules.table.state'),
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      render: (text: boolean, record: SkillRule) => (
        <Switch
          size='small'
          checked={text}
          loading={switchLoading[record.id]}
          onChange={(checked) => handleSwitchChange(checked, record)}
        />
      ),
    },
    {
      title: t('skill.rules.table.actions'),
      key: 'actions',
      render: (text: any, record: SkillRule) => (
        <>
          <PermissionWrapper
            requiredPermissions={['Edit']}>
            <Button type="link" onClick={() => handleEdit(record)}>
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper
            requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('skill.rules.deleteConfirm')}
              onConfirm={() => handleDeleteRule(record.id)}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
            >
              <Button type="link" danger>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </PermissionWrapper>
        </>
      ),
    },
  ];

  return (
    <div className='h-full flex flex-col'>
      <div className='mb-[20px] flex items-center justify-end'>
        <Search
          placeholder={`${t('common.search')}...`}
          allowClear
          onSearch={handleSearch}
          enterButton
          className='w-60 mr-2'
        />
        <PermissionWrapper
          requiredPermissions={['Add']}>
          <Button icon={<PlusOutlined />} type="primary" onClick={handleAdd}>{t('common.add')}</Button>
        </PermissionWrapper>
      </div>
      <div className='flex-grow'>
        {loading ? (
          <div className='w-full flex items-center justify-center min-h-72'>
            <Spin size="large" />
          </div>
        ) : (
          <Table
            rowKey='id'
            size="middle"
            dataSource={data}
            columns={columns}
            pagination={false}
            scroll={{ y: 'calc(100vh - 370px)' }}
          />
        )}
      </div>
      <div className='fixed bottom-8 right-8'>
        {!loading && total > 0 && (
          <Pagination
            total={total}
            showSizeChanger
            current={pagination.current}
            pageSize={pagination.pageSize}
            onChange={handleTableChange}
            onShowSizeChange={handlePageSizeChange}
          />
        )}
      </div>
      <ModifyRuleModal
        visible={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={handleConfirmRule}
        initialValues={selectedSkillRule ? {
          key: selectedSkillRule.id,
          name: selectedSkillRule.name,
          description: selectedSkillRule.description,
          conditionsOperator: selectedSkillRule.condition?.operator,
          conditions: selectedSkillRule.condition?.conditions.map((condition: any) => ({
            ...condition,
            operator: 'include',
          })),
          action: selectedSkillRule.action,
          action_set: selectedSkillRule.action_set,
        } : null}
      />
    </div>
  );
};

export default SkillRules;
