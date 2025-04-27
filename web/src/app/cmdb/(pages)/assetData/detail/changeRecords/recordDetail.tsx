'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import { Button, Spin } from 'antd';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { deepClone, getFieldItem } from '@/app/cmdb/utils/common';
import CustomTable from '@/components/custom-table';
import recordDetailStyle from './recordDetail.module.scss';
import { RecordDetailProps, FieldModalRef, RecordsEnum } from '@/app/cmdb/types/assetData';

const RecordDetail = forwardRef<FieldModalRef, RecordDetailProps>(
  (
    { userList, propertyList, modelList, groupList, enumList, connectTypeList },
    ref
  ) => {
    const { t } = useTranslation();
    const { get } = useApiClient();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [subTitle, setSubTitle] = useState<string>('');
    const [title, setTitle] = useState<string>('');
    const [loading, setLoading] = useState<boolean>(false);
    const [recordRow, setRecordRow] = useState<any>({});
    const [formData, setFormData] = useState<any>({
      list: [
        { label: t('Model.action'), id: 'type' },
        { label: t('Model.modelType'), id: 'model_id' },
        { label: t('Model.operationExamples'), id: 'inst_id' },
        { label: t('Model.operationTime'), id: 'created_at' },
        { label: t('Model.operateAccount'), id: 'operator' },
      ],
      attrList: [],
      attrColumns: [
        {
          title: t('Model.attribute'),
          key: 'attr',
          dataIndex: 'attr',
          align: 'left',
          minWidth: '50',
        },
        {
          title: t('Model.beforeTheChange'),
          key: 'before',
          dataIndex: 'before',
          align: 'left',
          minWidth: '100px',
        },
        {
          title: t('Model.afterTheChange'),
          key: 'after',
          dataIndex: 'after',
          align: 'left',
          minWidth: '100px',
        },
      ],
    });
    const [instInfo, setInstInfo] = useState<RecordsEnum>({});

    useEffect(() => {
      if (groupVisible) {
        const form = deepClone(formData);
        form.attrList = [];
        setFormData(form);
      }
    }, [groupVisible]);

    useImperativeHandle(ref, () => ({
      showModal: ({ subTitle, title, recordRow }) => {
        // 开启弹窗的交互
        setGroupVisible(true);
        setSubTitle(subTitle);
        setTitle(title);
        setRecordRow(recordRow);
        getChangeRecordDetail(recordRow.id);
        if (recordRow.label === 'instance_association') {
          const form = deepClone(formData);
          form.attrColumns[0] = {
            title: t('Model.objectType'),
            key: 'attr',
            align: 'left',
            minWidth: '50',
          };
          setFormData(form);
        }
      },
    }));

    const getShowValue = (field: any, tex: any) => {
      return getFieldItem({
        fieldItem: field,
        userList,
        groupList,
        isEdit: false,
        value: tex[field.attr_id],
      });
    };

    const showModelName = (id: string) => {
      return modelList.find((item) => item.model_id === id)?.model_name || '--';
    };

    const showConnectType = (id: string) => {
      return (
        connectTypeList.find((item) => item.asst_id === id)?.asst_name || '--'
      );
    };

    const getDisplayName = (id: string) => {
      let label: any = recordRow[id] || '--';
      switch (id) {
        case 'type':
          label = enumList[label] || '--';
          break;
        case 'model_id':
          label =
            modelList.find((item) => item.model_id === label)?.model_name ||
            '--';
          break;
        case 'inst_id':
          label = instInfo.name;
          break;
      }
      return label;
    };
    const getChangeRecordDetail = async (detailId: number) => {
      try {
        setLoading(true);
        const data = await get(`/cmdb/api/change_record/${detailId}/`);
        const form = deepClone(formData);
        const {
          before_data: beforeData,
          after_data: afterData,
          label,
          type,
        } = data;
        if (label === 'instance') {
          setInstInfo({
            name: afterData?.inst_name || beforeData?.inst_name || '--',
          });
          const list = type === 'delete_entity' ? [] : afterData;
          form.attrList = Object.keys(list)
            .map((item, index) => {
              const field = propertyList.find((prop) => prop.attr_id === item);
              if (field) {
                field.key = field.attr_id;
                const beforTex: any = {};
                beforTex[item] = beforeData[item];
                const afterTex: any = {};
                afterTex[item] = afterData[item];
                return {
                  attr: field.attr_name,
                  id: index,
                  before: getShowValue(field, beforTex),
                  after: getShowValue(field, afterTex),
                };
              }
              return {
                attr: null,
              };
            })
            .filter((attr) => !!attr.attr);
        } else if (label.includes('credential')) {
          let before = '--';
          let after = '--';
          if (type === 'create_edge') {
            after = `${afterData.src.name}关联${showModelName(
              afterData.dst.model_id
            )}(${afterData.dst.inst_name})`;
          } else {
            before = `${beforeData.src.name}取消关联${showModelName(
              beforeData.dst.model_id
            )}(${beforeData.dst.inst_name})`;
          }
          form.attrList = [
            {
              attr: t('Model.relatedRelationships'),
              id: 1,
              before,
              after,
            },
          ];
          setInstInfo({
            name: beforeData.dst?.inst_name || afterData.dst?.inst_name || '--',
          });
        } else {
          let before = '--';
          let after = '--';
          form.attrList = data;
          if (type === 'delete_edge') {
            before = `${showModelName(beforeData.edge.src_model_id)}(${
              beforeData.src.inst_name
            }) ${showConnectType(beforeData.edge.asst_id)} ${showModelName(
              beforeData.edge.dst_model_id
            )}(${beforeData.dst.inst_name})`;
            setInstInfo({
              name:
                recordRow.model_id === beforeData.edge.src_model_id
                  ? beforeData.src.inst_name
                  : beforeData.dst.inst_name,
            });
          } else {
            after = `${showModelName(afterData.edge.src_model_id)}(${
              afterData.src.inst_name
            }) ${showConnectType(afterData.edge.asst_id)} ${showModelName(
              afterData.edge.dst_model_id
            )}(${afterData.dst.inst_name})`;
            setInstInfo({
              name:
                recordRow.model_id === afterData.edge.src_model_id
                  ? afterData.src.inst_name
                  : afterData.dst.inst_name,
            });
          }
          form.attrList = [
            {
              attr: t('Model.relatedRelationships'),
              id: 1,
              before,
              after,
            },
          ];
        }
        setFormData(form);
      } finally {
        setLoading(false);
      }
    };

    const handleCancel = () => {
      setGroupVisible(false);
    };

    return (
      <div>
        <OperateModal
          width={600}
          title={title}
          subTitle={subTitle}
          open={groupVisible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button onClick={handleCancel}>{t('cancel')}</Button>
            </div>
          }
        >
          <Spin spinning={loading}>
            <div className={recordDetailStyle.recordDetail}>
              <ul className={recordDetailStyle.description}>
                {formData.list.map((item: any, index: number) => {
                  return (
                    <li key={index} className={recordDetailStyle.desItem}>
                      <span className={recordDetailStyle.label}>
                        {item.label}：
                      </span>
                      <span
                        className={`${recordDetailStyle.name} text-[var(--color-text-3)]`}
                      >
                        {getDisplayName(item.id)}
                      </span>
                    </li>
                  );
                })}
              </ul>
              <CustomTable
                size="middle"
                scroll={{ y: 'calc(100vh - 500px)' }}
                columns={formData.attrColumns}
                dataSource={formData.attrList}
                rowKey="id"
              ></CustomTable>
            </div>
          </Spin>
        </OperateModal>
      </div>
    );
  }
);
RecordDetail.displayName = 'recordDetail';
export default RecordDetail;
