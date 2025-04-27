'use client';
import React, { useState, useEffect, useCallback } from 'react';
import { Button, Input, Form, message, Spin, Popconfirm } from 'antd';
import { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import TopSection from '@/components/top-section';
import OperateModal from '@/components/operate-modal';
import { OriginalGroup, ConvertedGroup } from '@/app/system-manager/types/group';
import { useTranslation } from '@/utils/i18n';
import { useGroupApi } from '@/app/system-manager/api/group/index';

const { Search } = Input;

const Groups: React.FC = () => {
  const [addForm] = Form.useForm();
  const [renameForm] = Form.useForm();
  const [addSubTeamKey, setAddSubTeamKey] = useState('');
  const [renameKey, setRenameKey] = useState('');
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);
  const [addTeamModalOpen, setAddTeamModalOpen] = useState(false);
  const [addSubTeamModalOpen, setAddSubTeamModalOpen] = useState(false);
  const [renameTeamModalOpen, setRenameTeamModalOpen] = useState(false);
  const [dataSource, setDataSource] = useState<ConvertedGroup[]>([]);
  const [originalData, setOriginalData] = useState<OriginalGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);

  const { t } = useTranslation();
  const { getTeamData, addTeamData, updateGroup, deleteTeam } = useGroupApi();

  const columns: ColumnsType<ConvertedGroup> = [
    { 
      title: t('system.group.form.name'), 
      dataIndex: 'name', 
      width: 450,
      render: (text: string, data: ConvertedGroup) => (
        <>
          {data.children && data.children.length > 0 ? (
            <span>{text}</span>
          ) : (
            text
          )}
        </>
      ),
    },
    {
      title: t('common.actions'),
      dataIndex: 'actions',
      width: 300,
      render: (_: string, data: ConvertedGroup) => (
        <>
          <Button type="link" className="mr-[8px]" onClick={() => addSubGroup(data.key)}>
            {t('system.group.addSubGroups')}
          </Button>
          <Button type="link" className="mr-[8px]" onClick={() => renameGroup(data.key)}>
            {t('system.group.rename')}
          </Button>
          {!data.children || data.children.length === 0 ? (
            <Popconfirm
              title={t('common.delConfirm')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => handleDeleteGroup(data.key)}
            >
              <Button type="link">{t('common.delete')}</Button>
            </Popconfirm>
          ) : null}
        </>
      ),
    },
  ];

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const teamData = await getTeamData();
      setOriginalData(teamData);
      const convertedData = convertGroups(teamData);
      setDataSource(convertedData);
    } finally {
      setLoading(false);
    }
  }, [getTeamData]);

  const convertGroups = (groups: OriginalGroup[]): ConvertedGroup[] => {
    return groups.map((group) => {
      const groupData: ConvertedGroup = {
        key: group.id,
        name: group.name,
      };

      if (group.subGroups && group.subGroups.length > 0) {
        groupData.children = convertGroups(group.subGroups);
      }

      return groupData;
    });
  };

  const handleInputSearchChange = async (value: string) => {
    setLoading(true);
    try {
      const filteredData = originalData.filter((group: any) => group.name.includes(value));
      const newData = convertGroups(filteredData);
      setDataSource(newData);
    } finally {
      setLoading(false);
    }
  };

  const addGroup = () => {
    setAddTeamModalOpen(true);
    addForm.resetFields();
  };

  const onAddTeam = async () => {
    setModalLoading(true);
    try {
      await addForm.validateFields();
      await addTeamData({
        group_name: addForm.getFieldValue('teamName'),
      });
      await fetchData();
      message.success(t('common.addSuccess'));
      setAddTeamModalOpen(false);
    } catch (error) {
      console.error('Failed:', error);
    } finally {
      setModalLoading(false);
    }
  };

  const addSubGroup = (key: string) => {
    setAddSubTeamModalOpen(true);
    setAddSubTeamKey(key);
    addForm.resetFields();
  };

  const onAddSubTeam = async () => {
    setModalLoading(true);
    try {
      await addForm.validateFields();
      const teamName = addForm.getFieldValue('teamName');
      await addTeamData({
        group_name: teamName,
        parent_group_id: addSubTeamKey,
      });
      await fetchData();
      message.success(t('common.addSuccess'));
      setExpandedRowKeys((prev) => [...prev, addSubTeamKey]);
      setAddSubTeamModalOpen(false);
    } catch (error) {
      console.error('Failed:', error);
    } finally {
      setModalLoading(false);
    }
  };

  const renameGroup = (key: string) => {
    setRenameTeamModalOpen(true);
    setRenameKey(key);
    renameForm.resetFields();
    const node = findNode(originalData, key);
    if (node) {
      renameForm.setFieldsValue({ renameTeam: node.name });
    }
  };

  const findNode = (treeData: OriginalGroup[], targetKey: string): OriginalGroup | undefined => {
    for (const node of treeData) {
      if (node.id === targetKey) {
        return node;
      } else if (node.subGroups) {
        const childNode = findNode(node.subGroups, targetKey);
        if (childNode) return childNode;
      }
    }
  };

  const onRenameTeam = async () => {
    setModalLoading(true);
    try {
      await renameForm.validateFields();
      const newName = renameForm.getFieldValue('renameTeam');
      await updateGroup({
        group_id: renameKey,
        group_name: newName,
      });
      message.success(t('system.group.renameSuccess'));
      await fetchData();
      setRenameTeamModalOpen(false);
    } catch (error) {
      console.error('Failed:', error);
    } finally {
      setModalLoading(false);
    }
  };

  const handleDeleteGroup = (key: string) => {
    const group = findNode(originalData, key);
    if (group) {
      deleteGroup(group);
    }
  };

  const deleteGroup = async (data: OriginalGroup) => {
    setLoading(true);
    try {
      await deleteTeam(data);
      message.success(t('common.delSuccess'));
      await fetchData();
    } finally {
      setLoading(false);
    }
  };

  const onExpand = (expanded: boolean, record: ConvertedGroup) => {
    setExpandedRowKeys((prev) => (expanded ? [...prev, record.key] : prev.filter((key) => key !== record.key)));
  };

  return (
    <div className="w-full flex flex-col">
      <TopSection title={t('system.group.title')} content={t('system.group.desc')} />
      <div className="mt-4 flex-1 h-full rounded-md overflow-hidden p-4 bg-[var(--color-bg)]">
        <div className="w-full mt-4 mb-4 flex justify-end">
          <Search
            allowClear
            enterButton
            className="w-60 mr-[8px]"
            onSearch={handleInputSearchChange}
            placeholder={`${t('common.search')}...`}
          />
          <Button type="primary" onClick={addGroup}>
            +{t('common.add')}
          </Button>
        </div>

        <Spin spinning={loading}>
          <CustomTable
            rowKey="key"
            pagination={false}
            expandedRowKeys={expandedRowKeys}
            onExpand={onExpand}
            scroll={{ y: 'calc(100vh - 330px)' }}
            columns={columns}
            dataSource={dataSource}
          />
        </Spin>
      </div>

      <OperateModal
        title={t('common.add')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        open={addTeamModalOpen}
        onOk={onAddTeam}
        onCancel={() => setAddTeamModalOpen(false)}
      >
        <Form form={addForm}>
          <Form.Item
            name="teamName"
            label={t('system.group.form.name')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.group.form.name')}`} />
          </Form.Item>
        </Form>
      </OperateModal>

      <OperateModal
        title={t('system.group.addSubGroups')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        open={addSubTeamModalOpen}
        onOk={onAddSubTeam}
        onCancel={() => setAddSubTeamModalOpen(false)}
      >
        <Form form={addForm}>
          <Form.Item
            name="teamName"
            label={t('system.user.form.name')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.user.form.name')}`} />
          </Form.Item>
        </Form>
      </OperateModal>

      <OperateModal
        title={t('system.group.rename')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        open={renameTeamModalOpen}
        onOk={onRenameTeam}
        onCancel={() => setRenameTeamModalOpen(false)}
      >
        <Form form={renameForm}>
          <Form.Item
            name="renameTeam"
            label={t('system.user.form.name')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.user.form.name')}`} />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
};

export default Groups;
