'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useRef,
} from 'react';
import { Button, message, Upload } from 'antd';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api';
import type { UploadProps } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import axios from 'axios';
import { useAuth } from '@/context/auth';
import { useSession } from 'next-auth/react';

interface FieldModalProps {
  onSuccess: () => void;
}

interface FieldConfig {
  subTitle: string;
  title: string;
  model_id: string;
}

export interface FieldModalRef {
  showModal: (info: FieldConfig) => void;
}

const ImportInst = forwardRef<FieldModalRef, FieldModalProps>(
  ({ onSuccess }, ref) => {
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [exportDisabled, setExportDisabled] = useState<boolean>(false);
    const [subTitle, setSubTitle] = useState<string>('');
    const [title, setTitle] = useState<string>('');
    const [modelId, setModelId] = useState<string>('');
    const [fileList, setFileList] = useState<any[]>([]);
    const { t } = useTranslation();
    const instanceApi = useInstanceApi();
    const { Dragger } = Upload;
    const authContext = useAuth();
    const { data: session } = useSession();
    const token = session?.user?.token || authContext?.token || null;
    const tokenRef = useRef(token);

    useImperativeHandle(ref, () => ({
      showModal: ({ subTitle, title, model_id }) => {
        // 开启弹窗的交互
        setGroupVisible(true);
        setSubTitle(subTitle);
        setTitle(title);
        setModelId(model_id);
        setFileList([]);
      },
    }));

    const handleSubmit = () => {
      operateAttr();
    };

    const exportTemplate = async () => {
      try {
        setExportDisabled(true);
        const response = await axios({
          url: `/api/proxy/cmdb/api/instance/${modelId}/download_template/`, // 替换为你的导出数据的API端点
          method: 'GET',
          responseType: 'blob', // 确保响应类型为blob
          headers: {
            Authorization: `Bearer ${tokenRef.current}`,
          },
        });
        // 创建一个Blob对象
        const blob = new Blob([response.data], {
          type: response.headers['content-type'],
        });
        // 创建一个下载链接
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `${modelId}导入模板.xlsx`; // 设置下载文件的名称
        document.body.appendChild(link);
        link.click();
        // 移除下载链接
        document.body.removeChild(link);
      } catch (error: any) {
        message.error(error.message);
      } finally {
        setExportDisabled(false);
      }
    };

    const handleChange: UploadProps['onChange'] = ({ fileList }) => {
      setFileList(fileList);
    };

    const customRequest = async (options: any) => {
      const { onSuccess } = options;
      onSuccess('Ok');
    };

    const operateAttr = async () => {
      const fmData = new FormData();
      fmData.append('file', fileList[0].originFileObj);
      try {
        setConfirmLoading(true);
        await instanceApi.importInstances(modelId, fmData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        });
        message.success('导入成功');
        onSuccess();
        handleCancel();
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleCancel = () => {
      setGroupVisible(false);
    };

    return (
      <div>
        <OperateModal
          title={title}
          subTitle={subTitle}
          visible={groupVisible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                loading={confirmLoading}
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <div>
            <Dragger
              customRequest={customRequest}
              onChange={handleChange}
              fileList={fileList}
              accept=".xls,.xlsx"
              maxCount={1}
              className="w-full"
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">{t('uploadAction')}</p>
              <p className="ant-upload-hint">{t('Model.uploadDescription')}</p>
            </Dragger>
            <Button
              disabled={exportDisabled}
              className="mt-[10px]"
              type="link"
              onClick={exportTemplate}
            >
              {t('exportTemplate')}
            </Button>
          </div>
        </OperateModal>
      </div>
    );
  }
);
ImportInst.displayName = 'importInst';
export default ImportInst;
