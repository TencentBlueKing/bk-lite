"use client"
import PageLayout from '@/components/page-layout';
import CustomTable from '@/components/custom-table';
import TopSection from '@/components/top-section';
import { ColumnItem } from '@/types';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import {
  Input,
  Button,
  Tree,
  Spin,
  Dropdown,
  Menu,
  Modal,
  message,
  Popconfirm,
  Switch,
} from 'antd';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import PermissionWrapper from '@/components/permission';
import { PlusOutlined, MoreOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import { useEffect, useState, useRef, useMemo } from 'react';
import usePlayroundApi from '@/app/playground/api';
import CategoryManageModal from './categoryManageModal';
import SampleManageModal from './sampleManageModal';
import { ModalRef, Pagination, TableData } from '@/app/playground/types';
const { Search } = Input;
const { confirm } = Modal;

const PlaygroundManage = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const {
    getCategoryList,
    getCapabilityList,
    deleteCapability,
    getAllSampleFileList,
    updateSampleFile,
    deleteSampleFile
  } = usePlayroundApi();
  const categoryModalRef = useRef<ModalRef>(null);
  const sampleModalRef = useRef<ModalRef>(null);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [selectCapability, setSelectCapability] = useState<number[]>([]);
  const [selectType, setSelectType] = useState<string>('');
  const [tableData, setTableData] = useState<TableData[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  })
  const [filteredTreeData, setFilteredTreeData] = useState<TreeDataNode[]>([]);
  const columns: ColumnItem[] = [
    {
      title: t(`common.name`),
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: t(`manage.createAt`),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (_, record) => {
        return (<p>{convertToLocalizedTime(record.created_at, 'YYYY-MM-DD HH:mm:ss')}</p>)
      }
    },
    {
      title: t(`manage.createdBy`),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 150,
      render: (_, { created_by }) => {
        return created_by ? (
          <div className="flex h-full items-center" title={created_by}>
            <span
              className="block w-[18px] h-[18px] leading-[18px] text-center content-center rounded-[50%] mr-2 text-white"
              style={{ background: 'blue' }}
            >
              {created_by.slice(0, 1).toLocaleUpperCase()}
            </span>
            <span>
              <EllipsisWithTooltip
                className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
                text={created_by}
              />
            </span>
          </div>
        ) : (
          <>--</>
        );
      }
    },
    {
      title: t(`manage.sampleStatus`),
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (_, record) => {
        return <PermissionWrapper requiredPermissions={['Edit']}>
          <Switch checked={record.is_active} onChange={(value: boolean) => handleSampleActiveChange(record?.id, value)} />
        </PermissionWrapper>
      }
    },
    {
      title: t(`common.action`),
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (_, record) => {
        return (
          <>
            <PermissionWrapper requiredPermissions={['Delete']}>
              <Popconfirm
                title={t(`manage.delCapability`)}
                description={t(`manage.delCapabilityText`)}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                okButtonProps={{ loading: confirmLoading }}
                onConfirm={() => handleDelSampleFile(record.id)}
              >
                <Button type='link' danger>{t(`common.delete`)}</Button>
              </Popconfirm>
            </PermissionWrapper>
          </>
        )
      }
    }
  ];

  const CapabilityMenuItems = [
    {
      key: 'update',
      label: <PermissionWrapper requiredPermissions={['Capability Edit']}>{t(`common.update`)}</PermissionWrapper>
    },
    {
      key: 'delete',
      label: <PermissionWrapper requiredPermissions={['Capability Delete']}>{t(`common.delete`)}</PermissionWrapper>,
    }
  ];

  const pageData = useMemo(() => {
    const items = tableData.filter((item: any) => {
      const [capability] = selectCapability
      return item?.capability === capability;
    });

    setPagination((prev) => ({ ...prev, total: items.length }));
    return items.slice((pagination.current - 1) * pagination.pageSize, pagination.pageSize);;

  }, [tableData, selectCapability, pagination.current, pagination.pageSize]);

  useEffect(() => {
    getAllTreeData();
    getAllSampleFile();
  }, []);

  const renderCapabilityNode = (categoryID: number, capabilityData: any[], categoryType: string) => {
    const filterData = capabilityData.filter(item => {
      const { id } = item.category;
      return categoryID === id;
    });
    return filterData.map((item: any) => ({
      key: item?.id,
      title: renderCapabilityTitle({ ...item, categoryType }),
      ...item
    }));
  };

  const findIDByName = (name: string, categoryList: any[]) => {
    const item = categoryList.find((item: any) => item.name === name);
    return item?.id;
  };

  const getAllTreeData = async () => {
    setTreeLoading(true);
    try {
      const capabilityData = await getCapabilityList();
      const categoryData = await getCategoryList();
      const nodes = [
        {
          key: 'model_experience',
          name: 'model_experience',
          selectable: false,
          title: t(`manage.modelExperience`),
          children: [
            {
              key: 'anomaly_detection',
              name: 'anomaly_detection',
              selectable: false,
              title: renderTitle({ name: t(`manage.anomalyDetection`), categoryID: findIDByName('异常检测', categoryData), categoryType: 'anomaly_detection' }),
              children: renderCapabilityNode(findIDByName('异常检测', categoryData), capabilityData, 'anomaly_detection')
            },
            {
              key: 'timeseries_predict',
              name: 'timeseries_predict',
              selectable: false,
              title: renderTitle({ name: t(`manage.timeseriesPredict`), categoryID: findIDByName('时序预测', categoryData), categoryType: 'timeseries_predict' }),
              children: renderCapabilityNode(findIDByName('时序预测', categoryData), capabilityData, 'timeseries_predict')
            },
            {
              key: 'log_clustering',
              name: 'log_clustering',
              selectable: false,
              title: renderTitle({ name: t(`manage.logClustering`), categoryID: findIDByName('日志聚类', categoryData), categoryType: 'log_clustering' }),
              children: renderCapabilityNode(findIDByName('日志聚类', categoryData), capabilityData, 'log_clustering')
            },
            {
              key: 'classification',
              name: 'classification',
              selectable: false,
              title: renderTitle({ name: t(`manage.classification`), categoryID: findIDByName('分类任务', categoryData), categoryType: 'classification' }),
              children: renderCapabilityNode(findIDByName('分类任务', categoryData), capabilityData, 'classification')
            }
          ]
        },
        {
          key: 'agent_experience',
          name: 'agent_experience',
          selectable: false,
          title: t(`manage.intelligentExperience`)
        }
      ];
      setFilteredTreeData(nodes);
    } catch (e) {
      console.log(e)
    } finally {
      setTreeLoading(false);
    }
  };

  const getAllSampleFile = async (name = '') => {
    setTableLoading(true);
    try {
      const { items } = await getAllSampleFileList({ name, page: pagination.current, page_size: pagination.pageSize });
      const data = items?.map((item: any) => ({
        id: item?.id,
        name: item?.name,
        created_at: item?.created_at,
        created_by: item?.created_by,
        is_active: item?.is_active,
        capability: item?.capability
      }));
      setTableData(data);

    } catch (e) {
      console.log(e);
      message.error(t(`manage.getSampleFileError`));
    } finally {
      setTableLoading(false);
    }
  };

  const renderCapabilityTitle = (data: any) => {
    return (
      <div className='w-full flex justify-between'>
        <span className='truncate'>{data?.name || '--'}</span>
        <span>
          <Dropdown
            overlay={
              <Menu
                onClick={(e) => e.domEvent.preventDefault()}

              >
                {CapabilityMenuItems?.map((item: any) => (
                  <Menu.Item
                    key={item.key}
                    className='!p-0'
                    onClick={() => {
                      if (item.key !== 'delete') {
                        openCategoryModal({ type: `${item.key}Capability`, title: `${item.key}Capability`, form: data })
                      } else {
                        handleDelCapability(data?.id)
                      }
                    }}
                  >
                    <PermissionWrapper requiredPermissions={['Capability Edit']} className='!block'>
                      <Button type='text' className='w-full'>{t(`common.${item.key}`)}</Button>
                    </PermissionWrapper>
                  </Menu.Item>
                ))}
              </Menu>
            }
            trigger={['click']}
          >
            <MoreOutlined
              className="cursor-pointer"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
              }}
            />
          </Dropdown>
        </span>
      </div>
    );
  };

  const renderTitle = (data: any) => {
    return (
      <div className='w-full flex justify-between'>
        <span className='truncate'>{data?.name || '--'}</span>
        <span>
          <Dropdown
            overlay={
              <Menu
                onClick={(e) => e.domEvent.preventDefault()}
              >
                <Menu.Item
                  className='!p-0'
                  onClick={() => {
                    openCategoryModal({ type: `addCapability`, title: `addCapability`, form: { categoryID: data?.categoryID, categoryType: data?.categoryType } })
                  }}>
                  <PermissionWrapper requiredPermissions={['Capability Add']} className='!block'>
                    <Button type='text' className='w-full'>{t(`common.add`)}</Button>
                  </PermissionWrapper>
                </Menu.Item>
              </Menu>
            }
            trigger={['click']}
          >
            <MoreOutlined
              className="cursor-pointer"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
              }}
            />
          </Dropdown>
        </span>
      </div>
    )
  };

  const renderTreeNode = () => {
    return filteredTreeData
  };

  const openCategoryModal = (data: {
    type: string;
    title: string;
    form: any
  }) => {
    categoryModalRef.current?.showModal(data)
  };

  const openSampleModal = (data: {
    type: string;
    title: string;
    form: any
  }) => {
    sampleModalRef.current?.showModal(data);
  };

  const onSelect = (keys: any[], info: any) => {

    try {
      const { categoryType } = info.node.config;
      if (keys.length) setSelectCapability(keys);
      if(!categoryType) setSelectType('');
      setSelectType(categoryType);
      
    } catch (e) {
      console.log(e);
    }
  };

  const handleSampleActiveChange = async (id: number, checked: boolean) => {
    setTableLoading(true);
    try {
      const params = {
        is_active: checked
      };
      await updateSampleFile(id, params);
    } catch (e) {
      console.log(e);
      message.error(t(`common.updateFailed`));
    } finally {
      getAllSampleFile();
    }
  };

  const handleChange = (value: any) => {
    setPagination(value);
  };

  const topSection = (
    <TopSection title={t(`manage.manageTitle`)} content={t(`manage.description`)} />
  );

  const leftSection = (
    <div className={`w-full h-full flex flex-col`}>
      <Spin spinning={treeLoading}>
        <div className='min-h-[370px] overflow-auto'>
          <Tree
            className="w-full flex-1"
            showLine
            blockNode
            expandAction={false}
            defaultExpandAll
            autoExpandParent
            selectedKeys={selectCapability}
            treeData={renderTreeNode()}
            onSelect={onSelect}
          />
        </div>
      </Spin>
    </div>
  );

  const onSearch = (search: string) => {
    getAllSampleFile(search);
  };

  const handleDelCapability = async (id: number) => {
    confirm({
      title: t(`manage.delCategory`),
      okText: t(`common.confirm`),
      cancelText: t(`common.cancel`),
      onOk: async () => {
        setConfirmLoading(true);
        try {
          await deleteCapability(id);
          message.success(t(`common.delSuccess`));
          setSelectCapability([]);
        } catch (e) {
          console.log(e);
        } finally {
          getAllTreeData();
        }
      }
    });
  };

  const handleDelSampleFile = async (id: number) => {
    setConfirmLoading(true);
    try {
      await deleteSampleFile(id);
    } catch (e) {
      console.log(e);
      message.error(t(`common.delFailed`));
    } finally {
      setConfirmLoading(false);
      getAllSampleFile();
    }
  };

  const rightSection = (
    <>
      <div className='flex justify-end mb-4'>
        <Search className='w-[240px] mr-4' placeholder={t(`common.search`)} enterButton onSearch={onSearch} />
        <PermissionWrapper requiredPermissions={['Add']}>
          <Button
            type='primary'
            disabled={selectCapability.length === 0}
            icon={<PlusOutlined />}
            onClick={() => openSampleModal({ type: 'add', title: 'add', form: { capability: selectCapability, categoryType: selectType } })}>
            {t(`common.add`)}
          </Button>
        </PermissionWrapper>
      </div>
      <CustomTable
        rowKey='id'
        scroll={{ y: 'calc(100vh - 420px)' }}
        columns={columns}
        loading={tableLoading}
        dataSource={pageData}
        pagination={pagination}
        onChange={handleChange}
      />
    </>
  );

  const onSuccess = () => {
    getAllTreeData();
  };

  return (
    <>
      <PageLayout
        rightSection={rightSection}
        leftSection={leftSection}
        topSection={topSection}
      />
      <CategoryManageModal ref={categoryModalRef} onSuccess={onSuccess} />
      <SampleManageModal ref={sampleModalRef} onSuccess={getAllSampleFile} />
    </>
  )
};

export default PlaygroundManage;