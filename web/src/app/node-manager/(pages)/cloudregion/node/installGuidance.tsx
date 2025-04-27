'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { Button } from 'antd';
import OperateDrawer from '@/app/node-manager/components/operate-drawer';
import { ModalRef } from '@/app/node-manager/types';
import { useTranslation } from '@/utils/i18n';
import CodeEditor from '@/app/node-manager/components/codeEditor';

const InstallGuidance = forwardRef<ModalRef>(({}, ref) => {
  const { t } = useTranslation();
  const [groupVisible, setGroupVisible] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [script, setScript] = useState<string>('');

  useImperativeHandle(ref, () => ({
    showModal: ({ title, form }) => {
      setGroupVisible(true);
      setTitle(title || '');
      setScript(form?.message);
    },
  }));

  const handleCancel = () => {
    setGroupVisible(false);
  };

  return (
    <div>
      <OperateDrawer
        width={700}
        title={title}
        visible={groupVisible}
        onClose={handleCancel}
        footer={
          <div>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <CodeEditor
          readOnly
          showCopy
          value={script}
          width="100%"
          height="calc(100vh - 180px)"
          mode="python"
          theme="monokai"
          name="editor"
        />
      </OperateDrawer>
    </div>
  );
});
InstallGuidance.displayName = 'InstallGuidance';
export default InstallGuidance;
