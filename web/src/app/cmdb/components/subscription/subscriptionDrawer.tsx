import React, { useEffect, useRef, useState } from 'react';
import { Button, Drawer, Input, Modal, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSubscriptionList, useSubscriptionMutation } from '@/app/cmdb/hooks/useSubscription';
import SubscriptionRuleList from './subscriptionRuleList';
import SubscriptionRuleForm, { type SubscriptionRuleFormRef } from './subscriptionRuleForm';
import type { QuickSubscribeDefaults, SubscriptionRule } from '@/app/cmdb/types/subscription';

interface SubscriptionDrawerProps {
  open: boolean;
  onClose: () => void;
  modelId: string;
  modelName: string;
  quickDefaults?: QuickSubscribeDefaults;
}

const SubscriptionDrawer: React.FC<SubscriptionDrawerProps> = ({
  open,
  onClose,
  modelId,
  modelName,
  quickDefaults,
}) => {
  const { t } = useTranslation();
  const { rules, loading, pagination, fetchRules, refresh } = useSubscriptionList();
  const { submitting, createRule, updateRule, deleteRule, toggleRule } = useSubscriptionMutation();
  const [search, setSearch] = useState('');
  const [editingRule, setEditingRule] = useState<SubscriptionRule | undefined>();
  const [formOpen, setFormOpen] = useState(false);
  const formRef = useRef<SubscriptionRuleFormRef>(null);

  useEffect(() => {
    if (open) {
      fetchRules({ page: 1, page_size: 10, name: '' });
      setSearch('');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    if (quickDefaults?.source && quickDefaults.source !== 'drawer') {
      setEditingRule(undefined);
      setFormOpen(true);
      return;
    }

    setFormOpen(false);
    setEditingRule(undefined);
  }, [open, quickDefaults?.source]);

  const handleSearch = (value: string) => {
    setSearch(value);
    fetchRules({ page: 1, page_size: pagination.pageSize, name: value });
  };

  const onSubmit = async (payload: any, enabled: boolean) => {
    if (editingRule) {
      await updateRule(editingRule.id, payload);
    } else {
      await createRule({ ...payload, is_enabled: enabled });
    }
    setFormOpen(false);
    setEditingRule(undefined);
    await refresh();
  };

  return (
    <Drawer
      open={open}
      width={830}
      onClose={() => {
        setFormOpen(false);
        setEditingRule(undefined);
        onClose();
      }}
      title={t('subscription.ruleManagement')}
      destroyOnClose
    >
      <div className="flex items-center justify-between gap-2 mb-4">
        <Input.Search
          placeholder={t('common.search')}
          allowClear
          style={{ width: 240 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onSearch={handleSearch}
        />
        <Button
          type="primary"
          onClick={() => {
            setEditingRule(undefined);
            setFormOpen(true);
          }}
        >
          {t('subscription.createRule')}
        </Button>
      </div>

      <SubscriptionRuleList
        rules={rules}
        loading={loading}
        pagination={pagination}
        onPageChange={(page, pageSize) => fetchRules({ page, page_size: pageSize, name: search })}
        onEdit={(rule) => {
          setEditingRule(rule);
          setFormOpen(true);
        }}
        onDelete={async (id) => {
          await deleteRule(id);
          await refresh();
        }}
        onToggle={async (id) => {
          await toggleRule(id);
          await refresh();
        }}
      />

      <Modal
        open={formOpen}
        width={800}
        title={editingRule ? t('subscription.editRule') : t('subscription.createRule')}
        centered
        onCancel={() => {
          setFormOpen(false);
          setEditingRule(undefined);
        }}
        footer={(
          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button
              type="primary"
              loading={submitting}
              onClick={() => void formRef.current?.submit(true)}
            >
              {t('subscription.saveAndEnable')}
            </Button>
            <Button
              loading={submitting}
              onClick={() => void formRef.current?.submit(false)}
            >
              {t('subscription.saveOnly')}
            </Button>
            <Button
              onClick={() => {
                setFormOpen(false);
                setEditingRule(undefined);
              }}
            >
              {t('subscription.cancel')}
            </Button>
          </Space>
        )}
        destroyOnClose
        styles={{
          body: {
            maxHeight: 'calc(100vh - 220px)',
            overflowY: 'auto',
            paddingTop: 24,
            paddingLeft: 24,
            paddingRight: 24,
          },
        }}
      >
        <SubscriptionRuleForm
          ref={formRef}
          initialValues={editingRule}
          quickDefaults={quickDefaults}
          modelId={modelId}
          modelName={modelName}
          onSubmitAndEnable={(data) => onSubmit(data, true)}
          onSubmitOnly={(data) => onSubmit(data, false)}
        />
      </Modal>
    </Drawer>
  );
};

export default SubscriptionDrawer;
