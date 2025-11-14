import { useTranslation } from "@/utils/i18n";
import { Spin, message, Image, Button, Input, Upload, type UploadProps, type UploadFile, Tag, } from "antd";
import React, { useEffect, useState, useMemo, useRef } from "react";
import useMlopsManageApi from "@/app/mlops/api/manage";
import { useSearchParams } from "next/navigation";
import { LeftOutlined, RightOutlined, PlusOutlined, SearchOutlined, MinusCircleOutlined } from "@ant-design/icons";
import PermissionWrapper from '@/components/permission';
import styles from './index.module.scss';
import { generateUniqueRandomColor } from "@/app/mlops/utils/common";

interface TrainDataItem {
  image_name: string;
  image_url: string;
  label?: string;
  predicted_label?: string;
}

interface LabelItem {
  id: number;
  name: string;
}

const ImageContent = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { getImageClassificationTrainDataInfo, updateImageClassificationTrainData } = useMlopsManageApi();
  const [trainData, setTrainData] = useState<TrainDataItem[]>([]);
  // const [fileList, setFileList] = useState<UploadFile<any>[]>([]);
  const [labels, setLabels] = useState<LabelItem[]>([
    { id: 1, name: 'fruit' },
    { id: 2, name: 'War' },
    { id: 3, name: 'Musical' },
    { id: 4, name: 'Family' },
    { id: 5, name: 'Sport' },
    { id: 6, name: 'Thriller' },
    { id: 7, name: 'Music' },
    { id: 8, name: 'Romance' },
    { id: 9, name: 'Drama' },
    { id: 10, name: 'Fantasy' },
  ]);
  const [currentIndex, setCurrentIndex] = useState(0);
  // const [activeTab, setActiveTab] = useState('unlabeled');
  const [searchValue, setSearchValue] = useState('');
  const [loadingState, setLoadingState] = useState<{
    imageLoading: boolean,
    saveLoading: boolean,
    showAddLabel: boolean,
  }>({
    imageLoading: false,
    saveLoading: false,
    showAddLabel: false
  });
  const thumbnailContainerRef = useRef<HTMLDivElement>(null);

  const {
    id,
    // key
  } = useMemo(() => ({
    id: searchParams.get('id') || '',
    key: searchParams.get('activeTap')
  }), [searchParams]);

  // 渲染识别结果
  const rendenrLabelResult = useMemo(() => {
    return trainData[currentIndex]?.label || (
      <div className="mb-2">&lt;{t('datasets.selectLab')}&gt;</div>
    );
  }, [trainData, currentIndex]);

  const props: UploadProps = {
    name: 'file',
    showUploadList: false,
    onChange: ({ file }) => {
      console.log(file.status);
      if (file.status === 'uploading') {
        message.info(t('datasets.uploading'))
      }
      if (file.status === 'done') {
        addNewImage(file)
      }
    },
    beforeUpload: (file) => {
      const isPng = file.type === 'image/png' || file.name.endsWith('.png');
      const isLt2M = file.size / 1024 / 1024 < 2;
      if (!isPng) {
        message.error(t('datasets.uploadWarn'));
      }
      if (!isLt2M) {
        message.error(t('datasets.over2MB'));
      }

      return (isLt2M && isPng) || Upload.LIST_IGNORE;

    },
    accept: 'image/*',
  };

  useEffect(() => {
    getTrainDataInfo()
  }, [searchParams]);

  useEffect(() => {
    const container = thumbnailContainerRef.current;
    if(!container) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      container.scrollLeft += e.deltaY;
    };

    container.addEventListener('wheel', handleWheel, {passive: false});
    return () => container.removeEventListener('wheel', handleWheel);
  }, [])

  const getTrainDataInfo = async () => {
    setLoadingState((prev) => ({ ...prev, imageLoading: true }));
    try {
      const data = await getImageClassificationTrainDataInfo(id, true, true);
      const train_data = data.train_data || [];
      const meta_data = data.meta_data;
      const allData = train_data.map((item: any) => {
        const labelItem = meta_data.image_label?.find((i: any) => i?.image_url === item?.image_url);
        if (labelItem) {
          return {
            ...item,
            label: labelItem?.label
          }
        }
        return item;
      });
      setTrainData(allData);
    } catch (e) {
      console.log(e);
      message.error(t(`common.error`))
    } finally {
      setLoadingState((prev) => ({ ...prev, imageLoading: false }))
    }
  };

  // 切换到指定图片
  const goToSlide = (index: number) => {
    setCurrentIndex(index);
    // 滚动缩略图到可见区域
    scrollThumbnailIntoView(index);
  };

  // 上一张
  const handlePrev = () => {
    const newIndex = currentIndex > 0 ? currentIndex - 1 : trainData.length - 1;
    goToSlide(newIndex);
  };

  // 下一张
  const handleNext = () => {
    const newIndex = currentIndex < trainData.length - 1 ? currentIndex + 1 : 0;
    goToSlide(newIndex);
  };

  // 滚动缩略图到可见区域
  const scrollThumbnailIntoView = (index: number) => {
    if (thumbnailContainerRef.current) {
      const thumbnail = thumbnailContainerRef.current.children[index] as HTMLElement;
      if (thumbnail) {
        thumbnail.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
    }
  };

  // 添加标签
  const handleAddLabel = (event: React.KeyboardEvent<HTMLInputElement>) => {
    const value = event.currentTarget.value.trim();

    if(!value) {
      return;
    }

    if (labels.some(label => label.name === value)) {
      return;
    }

    setLabels(prev => [...prev,{
      id: prev.length > 0 ? Math.max(...prev.map(l => l.id)) + 1 : 1,
      name: value
    }]);
    setLoadingState(prev => ({ ...prev, showAddLabel: false }));
  };

  // 标注图片
  const handleLabelImage = (labelName: string) => {
    if (trainData.length === 0) return;

    const updatedData = [...trainData];
    updatedData[currentIndex] = {
      ...updatedData[currentIndex],
      label: labelName
    };
    setTrainData(updatedData);
    // message.success(`已标注为: ${labelName}`);

    // 自动跳转到下一张未标注的图片
    // const nextUnlabeledIndex = updatedData.findIndex((item, idx) => idx > currentIndex && !item.label);
    // if (nextUnlabeledIndex !== -1) {
    //   goToSlide(nextUnlabeledIndex);
    // }
  };



  // 过滤后的数据（预留用于后续Tab切换功能）
  // const filteredData = useMemo(() => {
  //   if (activeTab === 'labeled') {
  //     return trainData.filter(item => item.label);
  //   } else if (activeTab === 'unlabeled') {
  //     return trainData.filter(item => !item.label);
  //   }
  //   return trainData;
  // }, [trainData, activeTab]);

  // 统计信息
  // const stats = useMemo(() => {
  //   const unlabeled = trainData.filter(item => !item.label).length;
  //   const labeled = trainData.filter(item => item.label).length;
  //   return { unlabeled, labeled, total: trainData.length };
  // }, [trainData]);

  // 过滤标签
  const filteredLabels = useMemo(() => {
    if (!searchValue) return labels;
    return labels.filter(label =>
      label.name.toLowerCase().includes(searchValue.toLowerCase())
    );
  }, [labels, searchValue]);

  const deleteLabels = (event: React.MouseEvent, id: number) => {
    event.stopPropagation();

    const labelItem = labels.find(l => l.id === id);
    const hasUsed = trainData.some(item => item.label === labelItem?.name);
    
    if(hasUsed) {
      message.warning('该标签已被使用');
      return;
    }

    setLabels(prev => prev.filter(item => item.id !== id));
  }

  // 添加图片
  const addNewImage = async (file: UploadFile) => {
    setLoadingState(prev => ({ ...prev, imageLoading: true }));
    try {
      const formData = new FormData();
      if (file.originFileObj) {
        formData.append('images', file.originFileObj);
        await updateImageClassificationTrainData(id, formData);
        getTrainDataInfo();
        message.success(t('datasets.uploadSuccess'));
      }
    } catch (e) {
      console.log(e)
    } finally {
      setLoadingState(prev => ({ ...prev, imageLoading: false }))
    }
  };

  const handleCancel = () => { getTrainDataInfo() };
  const handleSave = async () => {
    setLoadingState(prev => ({ ...prev, saveLoading: true }));
    try {
      const image_label: any[] = [];
      trainData.forEach((item) => {
        if (item.label) {
          image_label.push({
            image_url: item.image_url,
            label: item.label
          })
        }
      });
      await updateImageClassificationTrainData(id, {
        meta_data: JSON.stringify({
          image_label
        })
      });
      getTrainDataInfo();
      message.success(t('datasets.saveSuccess'));
    } catch (e) {
      console.log(e);
      message.error(t('datasets.saveError'));
    } finally {
      setLoadingState(prev => ({ ...prev, saveLoading: false }));
    }
  };

  return (
    <div className={styles.container}>
      <Spin spinning={loadingState.imageLoading}>
        <div className="h-full flex gap-4">
          {/* 左侧主要区域 */}
          <div className="max-w-[80%] flex-1 flex flex-col gap-4" style={{ height: '100%' }}>
            {/* 主图展示区域 */}
            <div className="flex-1 flex gap-4" style={{ minHeight: 0 }}>
              {/* 图片轮播 */}
              <div className="flex-1 relative bg-gray-50 rounded overflow-hidden">
                {trainData.length > 0 ? (
                  <>
                    <Button
                      icon={<LeftOutlined />}
                      onClick={handlePrev}
                      className="absolute left-4 top-1/2 -translate-y-1/2 z-10"
                      shape="circle"
                      size="large"
                    />
                    <div className="w-full h-full relative flex items-center justify-center p-8">
                      <Image
                        alt={trainData[currentIndex]?.image_name || ''}
                        src={trainData[currentIndex]?.image_url || ''}
                        style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                      // preview={false}
                      />
                      <div className="absolute top-6 right-8">
                        {trainData[currentIndex]?.label &&
                          <Tag color={generateUniqueRandomColor()}>{trainData[currentIndex]?.label}</Tag>
                        }
                      </div>
                    </div>
                    <Button
                      icon={<RightOutlined />}
                      onClick={handleNext}
                      className="absolute right-4 top-1/2 -translate-y-1/2 z-10"
                      shape="circle"
                      size="large"
                    />
                  </>
                ) : (
                  <div className="text-gray-400 flex items-center justify-center h-full">{t('common.noData')}</div>
                )}
              </div>

              {/* 识别结果 */}
              <div className="w-[15%] bg-white p-2 border border-gray-200 rounded flex-shrink-0">
                <div className="font-medium mb-2">{t('datasets.labelResult')}</div>
                <div className="text-sm text-gray-500">
                  {rendenrLabelResult}
                </div>
              </div>
            </div>

            {/* 底部缩略图列表 */}
            <div className="h-[108px] bg-white border border-gray-200 rounded px-3 pt-3 flex-shrink-0">
              <div
                ref={thumbnailContainerRef}
                className="flex gap-2 overflow-x-auto"
                style={{ scrollBehavior: 'smooth' }}
              >
                {trainData.map((item, index) => (
                  <div
                    key={index}
                    onClick={() => goToSlide(index)}
                    className={
                      `relative flex-shrink-0 w-[120px] h-[80px] cursor-pointer border-2 rounded overflow-hidden transition-all ${currentIndex === index
                        ? 'border-blue-500 shadow-lg'
                        : 'border-gray-200 hover:border-blue-300'
                      } ${!item.label ? 'opacity-70' : ''}`
                    }
                  >
                    <Image
                      alt={item.image_name || ''}
                      src={item.image_url || ''}
                      className="w-full h-full object-cover"
                      preview={false}
                    />
                    {item.label && (
                      <div className="absolute bottom-0 left-0 right-0 bg-blue-500 bg-opacity-80 text-white text-xs px-1 py-0.5 text-center truncate">
                        {item.label}
                      </div>
                    )}
                    {!item.label && (
                      <div className="absolute top-1 right-1 bg-orange-500 text-white text-xs px-1 rounded">
                        {t('datasets.unlabeled')}
                      </div>
                    )}
                  </div>
                ))}
                {/* 添加图片按钮 */}
                <Upload {...props}>
                  <div
                    className="flex-shrink-0 w-[120px] h-[80px] border-2 border-dashed border-gray-300 rounded flex items-center justify-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-all"
                  >
                    <div className="text-center">
                      <PlusOutlined className="text-2xl text-gray-400 mb-1" />
                      <div className="text-xs text-gray-500">{t('datasets.addImage')}</div>
                    </div>
                  </div>
                </Upload>
              </div>
            </div>
          </div>

          {/* 右侧标签栏 */}
          <div className="w-[20%] bg-white border border-gray-200 rounded p-4 flex flex-col">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-medium text-sm">{t('datasets.tabBar')}</h3>
            </div>
            <div className="flex flex-col justify-center items-start mb-2 gap-1 py-1">
              {/* 搜索框 */}
              <Input
                placeholder={t('common.inputMsg')}
                prefix={<SearchOutlined />}
                value={searchValue}
                onChange={(e) => setSearchValue(e.target.value)}
              />
              <div>
                <a className="ml-1 text-blue-600 text-xs" onClick={() => { setLoadingState((prev) => ({ ...prev, showAddLabel: true })) }}>添加标签</a>
                {loadingState.showAddLabel &&
                  <Input className="text-xs" placeholder="按下回车添加" onPressEnter={(event) => handleAddLabel(event)} />
                }
              </div>
            </div>

            {/* 标签列表 */}
            <div className={`flex-1 overflow-y-auto ${styles.scrollbar_hidden}`}>
              <div className="space-y-2">
                {filteredLabels.map((label) => (
                  <div
                    key={label.id}
                    onClick={() => handleLabelImage(label.name)}
                    className="flex justify-between items-center px-2 py-1 border text-xs content-center border-gray-200 rounded cursor-pointer hover:bg-blue-50 hover:border-blue-400 transition-all"
                  >
                    {label.name}
                    <MinusCircleOutlined className="text-red-600" onClick={(e) => deleteLabels(e, label.id)} />
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-4">
              <Button className="mr-2" onClick={handleCancel}>{t('common.cancel')}</Button>
              <PermissionWrapper requiredPermissions={['File Edit']}>
                <Button type="primary" loading={loadingState.saveLoading} onClick={handleSave}>{t('common.save')}</Button>
              </PermissionWrapper>
            </div>
          </div>
        </div>
      </Spin>
    </div>
  )
};

export default ImageContent;