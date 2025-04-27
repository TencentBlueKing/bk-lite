'use client';

import React, { useState, useRef } from 'react';
import { Button, Form, Select, message, Spin } from 'antd';
import { TableDataItem } from '@/app/node-manager/types';
import { useTranslation } from '@/utils/i18n';
import CodeEditor from '@/app/node-manager/components/codeEditor';
import { DownloadOutlined } from '@ant-design/icons';
import { useAuth } from '@/context/auth';
import controllerInstallSyle from './index.module.scss';
import useApiCloudRegion from '@/app/node-manager/api/cloudregion';
import axios from 'axios';
const { Option } = Select;

const ManualInstall: React.FC<{ config: any }> = ({ config }) => {
  const { t } = useTranslation();
  const { getInstallCommand } = useApiCloudRegion();
  const authContext = useAuth();
  const token = authContext?.token || null;
  const tokenRef = useRef(token);
  const [sidecarPackageLoading, setSidecarPackageLoading] =
    useState<boolean>(false);
  const [loadingCommand, setLoadingCommand] = useState<boolean>(false);
  const [sidecar, setSidecar] = useState<string | null>(null);
  const [script, setScript] = useState<string>('');

  const download = async () => {
    try {
      const name = config.sidecarVersionList.find(
        (item: TableDataItem) => item.id === sidecar
      )?.name;
      setSidecarPackageLoading(true);
      // 发起请求，获取文件流
      const response = await axios({
        url: `/api/proxy/node_mgmt/api/package/download/${sidecar}/`,
        method: 'GET',
        responseType: 'blob', // 确保返回的是二进制数据
        headers: {
          Authorization: `Bearer ${tokenRef.current}`,
        },
      });
      // 获取文件的 blob 数据和后端返回的文件名
      const blob = response.data;
      // 从响应头中提取文件名和 MIME 类型（如果后端提供了这些信息）
      const contentDisposition = response.headers['content-disposition']; // 文件名信息一般在 Content-Disposition 头中
      let fileName = `${name}`; // 默认文件名
      if (contentDisposition) {
        const fileNameMatch = contentDisposition.match(/filename="?(.+)"?/);
        if (fileNameMatch && fileNameMatch[1]) {
          fileName = decodeURIComponent(fileNameMatch[1]); // 解码文件名，避免中文乱码
        }
      }
      const mimeType = blob.type || 'application/octet-stream'; // 如果后端没有返回 MIME 类型，使用通用的二进制类型
      // 创建下载链接并触发下载
      const url = URL.createObjectURL(new Blob([blob], { type: mimeType }));
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName; // 设置下载的文件名
      document.body.appendChild(link);
      link.click(); // 模拟点击下载
      document.body.removeChild(link);
      // 释放 URL 对象
      URL.revokeObjectURL(url);
      message.success(t('common.successfulDownloaded'));
    } catch (error: any) {
      message.error(error + '');
    } finally {
      setSidecarPackageLoading(false);
    }
  };

  const handleSidecarChange = async (value: string) => {
    setScript('');
    setSidecar(value);
    if (value) {
      setLoadingCommand(true);
      try {
        const params = {
          os: config.os,
          package_name: config.sidecarVersionList.find(
            (item: TableDataItem) => item.id === value
          )?.name,
        };
        const data = await getInstallCommand(params);
        setScript(data);
      } finally {
        setLoadingCommand(false);
      }
    }
  };

  return (
    <div>
      <Form component={false}>
        <Form.Item
          label={t('node-manager.cloudregion.node.installationGuide')}
          className="mb-0"
        >
          <div className={`${controllerInstallSyle.description} mb-[16px]`}>
            {t('node-manager.cloudregion.node.downloadTips')}
          </div>
          <div className="pl-[20px]">
            <Form.Item
              required
              label={t('node-manager.cloudregion.node.sidecarVersion')}
            >
              <Form.Item name="sidecar" noStyle>
                <Select
                  style={{
                    width: 400,
                  }}
                  showSearch
                  allowClear
                  placeholder={t('common.pleaseSelect')}
                  value={sidecar}
                  onChange={(value: string) => {
                    handleSidecarChange(value);
                  }}
                >
                  {(config.sidecarVersionList || []).map(
                    (item: TableDataItem) => (
                      <Option value={item.id} key={item.id}>
                        {item.version}
                      </Option>
                    )
                  )}
                </Select>
                <Button
                  type="link"
                  icon={<DownloadOutlined />}
                  disabled={!sidecar}
                  loading={sidecarPackageLoading}
                  onClick={download}
                >
                  {t('node-manager.cloudregion.node.downloadPackage')}
                </Button>
              </Form.Item>
            </Form.Item>
          </div>
        </Form.Item>
      </Form>
      <div className={`${controllerInstallSyle.description} mb-[16px]`}>
        {t('node-manager.cloudregion.node.scriptTips')}
      </div>
      <Spin className="w-full" spinning={loadingCommand}>
        <CodeEditor
          readOnly
          showCopy
          value={script}
          className="ml-[20px] mb-[16px]"
          width="100%"
          height={200}
          mode="python"
          theme="monokai"
          name="editor"
        />
      </Spin>
      <div className={`${controllerInstallSyle.description}`}>
        {t('node-manager.cloudregion.node.finishTips')}
      </div>
    </div>
  );
};

export default ManualInstall;
