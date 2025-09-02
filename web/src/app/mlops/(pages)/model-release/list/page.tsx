'use client';
import { useState, useRef, useEffect } from "react";
import useMlopsTaskApi from "@/app/mlops/api/task";
import useMlopsModelReleaseApi from "@/app/mlops/api/modelRelease";
import CustomTable from "@/components/custom-table";
import { useTranslation } from "@/utils/i18n";
import { Button, Popconfirm, Switch, message, Tree, type TreeDataNode } from "antd";
import { PlusOutlined } from '@ant-design/icons';
import PageLayout from '@/components/page-layout';
import TopSection from "@/components/top-section";
import ReleaseModal from "./releaseModal";
import PermissionWrapper from '@/components/permission';
import { ModalRef, Option, Pagination, TableData } from "@/app/mlops/types";
import { ColumnItem } from "@/types";
import { TrainJob } from "@/app/mlops/types/task";


const ModelRelease = () => {
  const { t } = useTranslation();
  const { getAnomalyTaskList } = useMlopsTaskApi();
  const { getAnomalyServingsList, deleteAnomalyServing, updateAnomalyServings } = useMlopsModelReleaseApi();
  const modalRef = useRef<ModalRef>(null);
  const [trainjobs, setTrainjobs] = useState<Option[]>([]);
  const [tableData, setTableData] = useState<TableData[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });

  const treeData: TreeDataNode[] = [
    {
      title: t(`model-release.title`),
      key: 'modelRelease',
      selectable: false,
      children: [
        {
          title: t(`datasets.anomaly`),
          key: 'anomaly',
        },
        {
          title: t(`datasets.rasa`),
          key: 'rasa'
        }
      ]
    }
  ];

  const columns: ColumnItem[] = [
    {
      title: t(`model-release.modelName`),
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: t(`model-release.modelDescription`),
      dataIndex: 'description',
      key: 'description'
    },
    {
      title: t(`model-release.publishStatus`),
      dataIndex: 'status',
      key: 'status',
      render: (_, record) => {
        return <Switch checked={record.status === 'active'} onChange={(value: boolean) => handleModelAcitve(record.id, value)} />
      }
    },
    {
      title: t(`common.action`),
      dataIndex: 'action',
      key: 'action',
      width: 180,
      render: (_, record: TableData) => (<>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button type="link" className="mr-2" onClick={() => handleEdit(record)}>{t(`common.edit`)}</Button>
        </PermissionWrapper>
        <PermissionWrapper requiredPermissions={['Delete']}>
          <Popconfirm
            title={t(`model-release.delModel`)}
            description={t(`model-release.delModelContent`)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" danger>{t(`common.delete`)}</Button>
          </Popconfirm>
        </PermissionWrapper>
      </>)
    }
  ];

  const topSection = (
    <TopSection title={t('model-release.title')} content={t('model-release.detail')} />
  );

  const leftSection = (
    <div className='w-full'>
      <Tree
        treeData={treeData}
        showLine
        selectedKeys={selectedKeys}
        defaultExpandedKeys={['modelRelease']}
      />
    </div>
  );

  useEffect(() => {
    setSelectedKeys(['anomaly']);
  }, []);

  useEffect(() => {
    getModelServings();
  }, [selectedKeys])

  const publish = (record: any) => {
    modalRef.current?.showModal({ type: 'add', form: record })
  };

  const handleEdit = (record: any) => {
    modalRef.current?.showModal({ type: 'edit', form: record });
  };

  const getModelServings = async () => {
    const [activeTypes] = selectedKeys;
    if (!activeTypes) return;
    setLoading(true);
    try {
      const params = {
        page: pagination.current,
        page_size: pagination.pageSize,
      };
      if (activeTypes === 'anomaly') {
        const [taskList, { count, items }] = await Promise.all([getAnomalyTaskList({}), getAnomalyServingsList(params)]);
        const _data = taskList.map((item: TrainJob) => ({
          label: item.name,
          value: item.id
        }));
        setTrainjobs(_data);
        setTableData(items);
        setPagination((prev) => ({
          ...prev,
          total: count
        }));
      }
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteAnomalyServing(id);
      getModelServings();
    } catch (e) {
      console.log(e);
      message.error(t(`common.delFailed`));
    }
  };

  const handleModelAcitve = async (id: number, value: boolean) => {
    setLoading(true);
    try {
      const status = value ? 'active' : 'inactive';
      await updateAnomalyServings(id, { status })
    } catch (e) {
      console.log(e);
      // message.error(t(``));
    } finally {
      getModelServings();
    }
  };

  return (
    <>
      <PageLayout
        topSection={topSection}
        leftSection={leftSection}
        rightSection={
          (
            <>
              <div className="flex justify-end mb-2">
                <PermissionWrapper requiredPermissions={['Add']}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => publish({})}>{t(`model-release.modelRelease`)}</Button>
                </PermissionWrapper>
              </div>
              <div className="flex-1 relative">
                <div className="absolute w-full">
                  <CustomTable
                    scroll={{ x: '100%', y: 'calc(100vh - 420px)' }}
                    columns={columns}
                    dataSource={tableData}
                    loading={loading}
                    rowKey='id'
                    pagination={pagination}
                  />
                </div>
              </div>
            </>
          )
        }
      />
      <ReleaseModal ref={modalRef} trainjobs={trainjobs} activeTag={selectedKeys} onSuccess={() => getModelServings()} />
    </>
  )
};

export default ModelRelease;