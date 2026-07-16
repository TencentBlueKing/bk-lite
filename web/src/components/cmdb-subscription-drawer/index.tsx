import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'antd';
import ContentFormDrawer from '@/components/content-form-drawer';
import OperateFormModal from '@/components/operate-form-modal';
import SearchActionBar from '@/components/search-action-bar';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import SubscriptionRuleList from './subscriptionRuleList';
import SubscriptionRuleForm, { type SubscriptionRuleFormRef } from './subscriptionRuleForm';
import type {
  SubscriptionListController,
  SubscriptionMutationController,
  SubscriptionRuleFormRuntime,
} from './runtime';
import type { QuickSubscribeDefaults, SubscriptionRule } from './types';

export interface SubscriptionDrawerProps {
  open: boolean;
  onClose: () => void;
  modelId: string;
  modelName: string;
  quickDefaults?: QuickSubscribeDefaults;
  subscriptionListController: SubscriptionListController;
  subscriptionMutationController: SubscriptionMutationController;
  formRuntime: SubscriptionRuleFormRuntime;
}

const SubscriptionDrawer: React.FC<SubscriptionDrawerProps> = ({
  open,
  onClose,
  modelId,
  modelName,
  quickDefaults,
  subscriptionListController,
  subscriptionMutationController,
  formRuntime,
}) => {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const { rules, loading, pagination, fetchRules, refresh } = subscriptionListController;
  const { submitting, createRule, updateRule, deleteRule, toggleRule } =
    subscriptionMutationController;
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

  const closeRuleForm = () => {
    setFormOpen(false);
    setEditingRule(undefined);
  };

  const handleRuleFormCancel = () =>
    guardClose(!!formRef.current?.isDirty(), closeRuleForm);

  return (
    <ContentFormDrawer
      open={open}
      width={830}
      maskClosable={false}
      onClose={() => {
        setFormOpen(false);
        setEditingRule(undefined);
        onClose();
      }}
      title={t('subscription.ruleManagement')}
      destroyOnClose
      hideFooter
    >
      <SearchActionBar
        searchProps={{
          placeholder: t('common.search'),
          value: search,
          className: 'w-[240px]',
          onChange: (e) => setSearch(e.target.value),
          onSearch: handleSearch,
        }}
        actions={(
          <Button
            type="primary"
            onClick={() => {
              setEditingRule(undefined);
              setFormOpen(true);
            }}
          >
            {t('subscription.createRule')}
          </Button>
        )}
      />

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

      <OperateFormModal
        open={formOpen}
        width={800}
        title={editingRule ? t('subscription.editRule') : t('subscription.createRule')}
        centered
        maskClosable={false}
        onCancel={handleRuleFormCancel}
        confirmText={t('subscription.saveAndEnable')}
        cancelText={t('subscription.cancel')}
        confirmLoading={submitting}
        secondaryActionsPosition="afterConfirm"
        secondaryActions={(
          <Button
            loading={submitting}
            onClick={() => void formRef.current?.submit(false)}
          >
            {t('subscription.saveOnly')}
          </Button>
        )}
        onConfirm={() => void formRef.current?.submit(true)}
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
          runtime={formRuntime}
          onSubmitAndEnable={(data) => onSubmit(data, true)}
          onSubmitOnly={(data) => onSubmit(data, false)}
        />
      </OperateFormModal>
    </ContentFormDrawer>
  );
};

export type { QuickSubscribeDefaults, SubscriptionRule } from './types';
export { default as SubscriptionRuleForm } from './subscriptionRuleForm';
export type {
  SubscriptionRuleFormProps,
  SubscriptionRuleFormRef,
} from './subscriptionRuleForm';
export type {
  SubscriptionListController,
  SubscriptionMutationController,
  SubscriptionRuleFormRuntime,
} from './runtime';
export default SubscriptionDrawer;
