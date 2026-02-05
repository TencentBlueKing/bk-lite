'use client'
import { ReloadOutlined, PlusOutlined, MinusCircleOutlined, SearchOutlined } from '@ant-design/icons';
import type { AnnotatorRef, ImageSample } from '@labelu/image-annotator-react';
import {
  Button,
  message,
  Modal,
  Spin,
  Tabs,
  Input,
  // Tag
} from 'antd';
import { useCallback, useEffect, useMemo, useState, useRef, forwardRef, Dispatch, SetStateAction } from 'react';
import { useSearchParams } from 'next/navigation';
import useMlopsManageApi from '@/app/mlops/api/manage';
import { useAuth } from '@/context/auth';
import JSZip from 'jszip';
import styles from './index.module.scss'
import { useTranslation } from '@/utils/i18n';
import { DatasetType } from '@/app/mlops/types';
import type { ObjectDetectionMetadata, YOLOAnnotation } from '@/app/mlops/types';
import { generateUniqueRandomColor } from '@/app/mlops/utils/common';
import { DEFAULT_LABELS } from '@/app/mlops/constants';

interface ObjectDetectionTrainData {
  width: number;
  height: number;
  image_url: string;
  image_name: string;
  image_size: number;
  batch_index: number;
  batch_total: number;
  content_type: string;
  type: string;
}

// 创建包装组件来正确转发ref
const ImageAnnotatorWrapper = forwardRef<AnnotatorRef, any>((props, ref) => {
  const [Component, setComponent] = useState<any>(null);
  const mountedRef = useRef(false);

  useEffect(() => {
    // 防止严格模式下的重复加载
    if (!mountedRef.current) {
      mountedRef.current = true;
      import('@labelu/image-annotator-react').then(mod => {
        setComponent(() => mod.Annotator);
      });
    }

    return () => {
      // 组件卸载时的清理
      mountedRef.current = false;
    };
  }, []);

  if (!Component) return null;

  return <Component ref={ref} {...props} />;
});

ImageAnnotatorWrapper.displayName = 'ImageAnnotatorWrapper';

// 默认标签配置（用于初始化）
const defaultRectLabels = DEFAULT_LABELS;

const ObjectDetection = ({
  // isChange,
  setIsChange
}: {
  isChange?: boolean;
  setIsChange: Dispatch<SetStateAction<boolean>>
}) => {
  const { t } = useTranslation();
  const authContext = useAuth();
  const annotatorRef = useRef<AnnotatorRef>(null);
  const searchParams = useSearchParams();
  const { getTrainDataInfo, updateObjectDetectionTrainData } = useMlopsManageApi();

  // 资源管理 refs
  const imageUrlsRef = useRef<string[]>([]);
  const imageBlobsRef = useRef<Map<string, Blob>>(new Map());

  // 标签管理状态
  const [rectLabels, setRectLabels] = useState<Array<{ id: number; name: string; color: string }>>(
    defaultRectLabels.map((name, index) => ({
      id: index + 1,
      name,
      color: ['#03ba18ba', '#ff00ff', '#2e5fff', '#662eff', '#ffb62e', '#ff2ea4'][index] || generateUniqueRandomColor()
    }))
  );
  const [polygonLabels, setPolygonLabels] = useState<Array<{ id: number; name: string; color: string }>>([
    { id: 1, name: 'house', color: '#8400ff' }
  ]);
  const [activeToolType, setActiveToolType] = useState<'rect' | 'polygon'>('rect');
  const [searchValue, setSearchValue] = useState('');
  const [showAddLabel, setShowAddLabel] = useState(false);
  const [labelModalOpen, setLabelModalOpen] = useState(false);

  const [config, setConfig] = useState<any>(null);
  const [currentSample, setCurrentSample] = useState<ImageSample | null>(null);
  const [loading, setLoading] = useState<boolean>(false)
  // const [casualType, setCasualType] = useState<string>('');
  const [trainData, setTrainData] = useState<ObjectDetectionTrainData[]>([]);
  const [metaData, setMetadata] = useState<ObjectDetectionMetadata>({
    format: 'YOLO',
    classes: defaultRectLabels,
    num_classes: defaultRectLabels.length,
    num_images: 0,
    labels: {},
    statistics: {
      total_annotations: 0,
      images_with_annotations: 0,
      images_without_annotations: 0,
      class_distribution: {}
    }
  })
  const fileId = searchParams.get('file_id') || '';

  // 清理ObjectURL的函数
  const cleanupImageUrls = useCallback(() => {
    imageUrlsRef.current.forEach(url => {
      URL.revokeObjectURL(url);
    });
    imageUrlsRef.current = [];
    imageBlobsRef.current.clear();
  }, []);

  // 动态生成config（基于标签状态）
  const buildConfig = useCallback(() => {
    return {
      width: 800,
      height: 600,
      image: {
        url: "",
        rotate: 0
      },
      rect: {
        minWidth: 1,
        minHeight: 1,
        labels: rectLabels.map(l => ({
          color: l.color,
          key: l.name.charAt(0).toUpperCase() + l.name.slice(1).replace(/_/g, '-'),
          value: l.name
        }))
      },
      polygon: {
        lineType: 'line',
        minPointAmount: 3,
        maxPointAmount: 100,
        edgeAdsorptive: false,
        labels: polygonLabels.map(l => ({
          color: l.color,
          key: l.name.charAt(0).toUpperCase() + l.name.slice(1),
          value: l.name
        }))
      },
    };
  }, [rectLabels, polygonLabels]);

  // 标签变化时更新config
  useEffect(() => {
    const newConfig = buildConfig();
    setConfig(newConfig);
  }, [rectLabels, polygonLabels, buildConfig]);

  useEffect(() => {
    if (fileId) {
      getObjectTrainDataInfo();
    }
  }, [fileId]);

  // 组件卸载时清理资源
  useEffect(() => {
    return () => {
      cleanupImageUrls();
    };
  }, [cleanupImageUrls]);


  const samples = useMemo(() => {
    const _images = trainData?.map((item, index) => {
      // 从 YOLO 格式读取标注数据
      const yoloAnnotations = metaData?.labels?.[item.image_name] || [];

      // 将 YOLO 格式转换为 Annotator 格式
      const rectAnnotations = yoloAnnotations.map((ann, annIndex) => {
        // YOLO 归一化坐标 → Annotator 像素坐标
        const x = (ann.x_center - ann.width / 2) * item.width;
        const y = (ann.y_center - ann.height / 2) * item.height;
        const width = ann.width * item.width;
        const height = ann.height * item.height;

        return {
          type: 'rect' as const,
          x: Math.max(0, x),  // 防止负值
          y: Math.max(0, y),
          width: Math.min(width, item.width - x),  // 防止越界
          height: Math.min(height, item.height - y),
          label: ann.class_name,
          id: `rect_${index}_${annIndex}_${Date.now()}`,
          order: annIndex
        };
      });

      return {
        id: index,
        name: item.image_name || '',
        url: item.image_url || '',
        data: {
          rect: rectAnnotations
        }
      };
    }) || [];

    // 当 samples 更新时，尝试恢复之前选中的图片
    if (_images.length > 0) {
      if (currentSample) {
        // 根据图片名称找回之前的图片（因为重新加载后 url 会变）
        const matchedImage = _images.find(img => img.name === currentSample.name);
        if (matchedImage && matchedImage.url !== currentSample.url) {
          setCurrentSample(matchedImage);
        }
      } else {
        // 首次加载，选中第一张
        setCurrentSample(_images[0]);
      }
    }

    return _images;
  }, [trainData, metaData]);

  // 发生变化时更新samples的标注数据
  const updateSamples = (labels: any, currentSample: ImageSample | null) => {
    if (!labels || !currentSample) return;

    const imageName = currentSample.name || '';
    const imageData = trainData.find(item => item.image_name === imageName);

    if (!imageData) return;

    const rectAnnotations = labels.rect || [];

    // Convert Annotator format → YOLO format
    const yoloAnnotations: YOLOAnnotation[] = rectAnnotations
      .filter((ann: any) => !!ann.label) // labels.rect 数组中的元素已经是 rect 类型，只需检查是否有 label
      .map((ann: any) => {
        const { x, y, width, height, label } = ann;

        // Annotator uses pixel coordinates, convert to normalized YOLO format
        const x_center = (x + width / 2) / imageData.width;
        const y_center = (y + height / 2) / imageData.height;
        const norm_width = width / imageData.width;
        const norm_height = height / imageData.height;

        const classId = rectLabels.findIndex(l => l.name === label);

        return {
          class_id: classId >= 0 ? classId : 0,
          class_name: label,
          x_center: Number(x_center.toFixed(6)),
          y_center: Number(y_center.toFixed(6)),
          width: Number(norm_width.toFixed(6)),
          height: Number(norm_height.toFixed(6))
        };
      });

    // Update metadata with new YOLO annotations
    setMetadata((prev) => {
      const newLabels = { ...prev.labels };
      newLabels[imageName] = yoloAnnotations;

      // Recalculate statistics
      const allAnnotations = Object.values(newLabels).flat();
      const classDistribution: Record<string, number> = {};

      allAnnotations.forEach(ann => {
        classDistribution[ann.class_name] = (classDistribution[ann.class_name] || 0) + 1;
      });

      const imagesWithAnnotations = Object.values(newLabels).filter(anns => anns.length > 0).length;

      const newMetaData = {
        ...prev,
        labels: newLabels,
        statistics: {
          total_annotations: allAnnotations.length,
          images_with_annotations: imagesWithAnnotations,
          images_without_annotations: prev.num_images - imagesWithAnnotations,
          class_distribution: classDistribution
        }
      };

      return newMetaData;
    });
  };

  const getCurrentAnnotations = () => {
    const current = annotatorRef.current?.getSample();
    const labels = annotatorRef.current?.getAnnotations();

    return {
      current,
      labels
    }
  };

  // 标签管理函数
  const getCurrentLabels = () => {
    switch (activeToolType) {
      case 'rect': return rectLabels;
      case 'polygon': return polygonLabels;
      default: return rectLabels;
    }
  };

  const setCurrentLabels = (labels: Array<{ id: number; name: string; color: string }>) => {
    switch (activeToolType) {
      case 'rect': setRectLabels(labels); break;
      case 'polygon': setPolygonLabels(labels); break;
    }
  };

  const handleAddLabel = (event: React.KeyboardEvent<HTMLInputElement>) => {
    const value = event.currentTarget.value.trim();
    if (!value) return;

    const currentLabels = getCurrentLabels();
    if (currentLabels.some(label => label.name === value)) {
      message.warning(t('datasets.labelExists') || '标签已存在');
      return;
    }

    const newLabel = {
      id: currentLabels.length > 0 ? Math.max(...currentLabels.map(l => l.id)) + 1 : 1,
      name: value,
      color: generateUniqueRandomColor()
    };

    setCurrentLabels([...currentLabels, newLabel]);
    setShowAddLabel(false);
    setIsChange(true);
    event.currentTarget.value = '';
  };

  const handleDeleteLabel = (event: React.MouseEvent, id: number) => {
    event.stopPropagation();

    const currentLabels = getCurrentLabels();
    const labelItem = currentLabels.find(l => l.id === id);

    // 检查标签是否被使用
    const allAnnotations = Object.values(metaData.labels || {}).flat();
    const hasUsed = allAnnotations.some(ann => ann.class_name === labelItem?.name);

    if (hasUsed) {
      message.warning(t('datasets.labelInUse') || '该标签已被使用');
      return;
    }

    setCurrentLabels(currentLabels.filter(item => item.id !== id));
    setIsChange(true);
  };

  const filteredLabels = useMemo(() => {
    const currentLabels = getCurrentLabels();
    if (!searchValue) return currentLabels;
    return currentLabels.filter(label =>
      label.name.toLowerCase().includes(searchValue.toLowerCase())
    );
  }, [searchValue, rectLabels, polygonLabels, activeToolType]);

  const onLoad = (engine: any) => {
    // 清理可能遗留的 DOM 元素
    engine.container.querySelectorAll('div').forEach((div: any) => {
      div.remove();
    });

    const updateSampleData = (eventName: string) => {
      const { current, labels } = getCurrentAnnotations()

      // const current = annotatorRef.current?.getSample();
      if (eventName !== 'imageChange') setIsChange(true);
      // 对于删除事件，需要延迟获取标注数据，等待状态更新完成
      if (eventName === 'delete') {
        setTimeout(() => {
          const labels = annotatorRef.current?.getAnnotations();
          if (current && (current?.url !== currentSample?.url)) {
            setCurrentSample(current);
            updateSamples(labels, current);
          } else {
            updateSamples(labels, currentSample)
          }
        }, 0);
      } else if (eventName === 'imageChange') {
        // 切换图片 - 不在此处保存标注，因为：
        // 1. mouseup/add/change 事件已经实时保存了数据
        // 2. imageChange 触发时，annotator 视图已经清空，getAnnotations() 会返回空数据
        // 3. 如果在此保存会用空数据覆盖之前的标注，导致数据丢失
        if (current) {
          setCurrentSample(current);
        }
      } else {
        // const labels = annotatorRef.current?.getAnnotations();
        updateSamplesData(current, labels);
      }
    };

    const updateSamplesData = (current: any, labels: any) => {
      if (current && current.url !== currentSample?.url) {
        setCurrentSample(current);
        updateSamples(labels, current);
      } else {
        updateSamples(labels, currentSample);
      }
    };

    // 绑定新的事件处理器
    const addHandler = () => updateSampleData('add');
    const deleteHandler = () => updateSampleData('delete');
    const changeHandler = () => updateSampleData('change');
    const mouseupHandler = () => updateSampleData('mouseup');
    const backgroundImageLoadHandler = () => updateSampleData('imageChange');

    engine.on('add', addHandler);
    engine.on('delete', deleteHandler);
    engine.on('change', changeHandler);
    engine.on('mouseup', mouseupHandler);
    engine.on('backgroundImageLoaded', backgroundImageLoadHandler);
  };


  const saveResult = async () => {
    setLoading(true);
    try {
      // 先保存当前图片的标注到 metaData
      const currentLabels = annotatorRef.current?.getAnnotations();
      if (currentSample && currentLabels) {
        updateSamples(currentLabels, currentSample);
      }

      // 使用 flushSync 确保状态同步更新（需要 import）
      // 或者等待下一个事件循环
      await new Promise(resolve => setTimeout(resolve, 100));

      // 读取最新的 metaData（通过 setMetadata 的回调来获取）
      let latestLabels: Record<string, YOLOAnnotation[]> = {};

      await new Promise<void>((resolve) => {
        setMetadata((prev) => {
          latestLabels = prev.labels || {};
          resolve();
          return prev; // 不修改状态，只读取
        });
      });

      // 重新计算统计信息
      const classDistribution: Record<string, number> = {};
      let totalAnnotations = 0;
      let imagesWithAnnotations = 0;
      let imagesWithoutAnnotations = 0;

      trainData.forEach((imageData) => {
        const imageName = imageData.image_name;
        const yoloAnnotations = latestLabels[imageName] || [];

        if (yoloAnnotations.length === 0) {
          imagesWithoutAnnotations++;
        } else {
          imagesWithAnnotations++;
          totalAnnotations += yoloAnnotations.length;

          // 统计类别分布
          yoloAnnotations.forEach((ann) => {
            classDistribution[ann.class_name] = (classDistribution[ann.class_name] || 0) + 1;
          });
        }
      });

      // 构建新的metadata结构（YOLO格式）
      const newMetaData: ObjectDetectionMetadata = {
        format: 'YOLO',
        classes: rectLabels.map(l => l.name),
        num_classes: rectLabels.length,
        num_images: trainData.length,
        labels: latestLabels,
        statistics: {
          total_annotations: totalAnnotations,
          images_with_annotations: imagesWithAnnotations,
          images_without_annotations: imagesWithoutAnnotations,
          class_distribution: classDistribution
        }
      };

      // 重新打包所有图片为ZIP
      const zip = new JSZip();

      trainData.forEach((item) => {
        const blob = imageBlobsRef.current.get(item.image_name);
        if (blob) {
          zip.file(item.image_name, blob);
        }
      });

      const zipBlob = await zip.generateAsync({
        type: 'blob',
        compression: 'DEFLATE',
        compressionOptions: {
          level: 6
        }
      });

      // 构建FormData上传
      const formData = new FormData();
      formData.append('train_data', zipBlob, 'train_data.zip');
      formData.append('metadata', JSON.stringify(newMetaData));

      // 调用更新接口
      await updateObjectDetectionTrainData(fileId, formData);
      setIsChange(false);
      message.success('标注已保存');

      // 重新加载数据（确保与后端同步）
      getObjectTrainDataInfo();
    } catch (e) {
      console.error('保存标注失败:', e);
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  const onError = useCallback((err: any) => {
    console.error('Error:', err);
    message.error(err.message);
  }, []);

  const requestEdit = useCallback(() => {
    // 允许其他所有编辑操作
    return true;
  }, []);

  const toolbarRight = useMemo(() => {
    return (
      <div className='flex items-center gap-2'>
        <Button type='primary' onClick={() => setLabelModalOpen(true)}>{t(`datasets.labelManagement`)}</Button>
        <Button type='primary' onClick={saveResult}>{t(`datasets.saveChanges`)}</Button>
        <ReloadOutlined onClick={() => getObjectTrainDataInfo()} />
      </div>
    )
  }, [t]);

  const getObjectTrainDataInfo = async () => {
    // 清理旧的ObjectURL
    cleanupImageUrls();

    setLoading(true);
    try {
      // 1. 获取metadata (不获取train_data，避免大量数据传输)
      const data = await getTrainDataInfo(fileId, DatasetType.OBJECT_DETECTION, false, true);

      const metadata: ObjectDetectionMetadata = data.metadata || {
        format: 'YOLO',
        classes: defaultRectLabels,
        num_classes: defaultRectLabels.length,
        num_images: 0,
        labels: {},
        statistics: {
          total_annotations: 0,
          images_with_annotations: 0,
          images_without_annotations: 0,
          class_distribution: {}
        }
      };

      // 更新标签列表（从metadata加载）
      if (metadata.classes && metadata.classes.length > 0) {
        const loadedLabels = metadata.classes.map((name, index) => ({
          id: index + 1,
          name,
          color: rectLabels[index]?.color || generateUniqueRandomColor()
        }));
        setRectLabels(loadedLabels);
      }

      // 2. 下载ZIP
      const response = await fetch(
        `/api/proxy/mlops/object_detection_train_data/${fileId}/download/`,
        {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${authContext?.token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(`下载失败: ${response.status}`);
      }

      const zipBlob = await response.blob();

      // 3. 解压ZIP
      const zip = await JSZip.loadAsync(zipBlob);
      const imageFiles: ObjectDetectionTrainData[] = [];
      const imageExtensions = /\.(jpg|jpeg|png|gif|bmp|webp)$/i;

      let batchIndex = 0;
      const entries = Object.entries(zip.files);
      const totalImages = entries.filter(([name, file]) => !file.dir && imageExtensions.test(name)).length;

      for (const [fileName, file] of entries) {
        if (file.dir) continue;
        if (!imageExtensions.test(fileName)) continue;

        const blob = await file.async('blob');
        const imageUrl = URL.createObjectURL(blob);

        // 保存ObjectURL和Blob
        imageUrlsRef.current.push(imageUrl);
        imageBlobsRef.current.set(fileName, blob);

        // 获取图片尺寸
        const dimensions = await new Promise<{ width: number; height: number }>((resolve) => {
          const img = new Image();
          img.onload = () => {
            resolve({ width: img.width, height: img.height });
          };
          img.onerror = () => {
            resolve({ width: 800, height: 600 }); // 默认尺寸
          };
          img.src = imageUrl;
        });

        imageFiles.push({
          width: dimensions.width,
          height: dimensions.height,
          image_name: fileName,
          image_url: imageUrl,
          image_size: blob.size,
          batch_index: batchIndex++,
          batch_total: totalImages,
          content_type: blob.type || 'image/jpeg',
          type: 'train' // 默认为训练集
        });
      }

      setTrainData(imageFiles);
      setMetadata(metadata);

    } catch (e) {
      console.error('加载训练数据失败:', e);
      message.error('加载失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <Spin spinning={loading}>
        <div className='h-full'>
          {samples.length > 0 && (
            <ImageAnnotatorWrapper
              ref={annotatorRef}
              toolbarRight={toolbarRight}
              primaryColor='#0d53de'
              samples={samples}
              offsetTop={222}
              editingSample={currentSample}
              onLoad={onLoad}
              onError={onError}
              config={config}
              disabled={false}
              requestEdit={requestEdit}
            />
          )}
        </div>
      </Spin>

      {/* 标签管理模态框 */}
      <Modal
        title={t('datasets.labelManagement') || '标签管理'}
        open={labelModalOpen}
        onCancel={() => setLabelModalOpen(false)}
        footer={null}
        width={600}
      >
        {/* 工具类型切换 */}
        <Tabs
          activeKey={activeToolType}
          onChange={(key) => setActiveToolType(key as any)}
          size="small"
          items={[
            { key: 'rect', label: 'Rect' },
            { key: 'polygon', label: 'Polygon' },
          ]}
        />

        {/* 搜索和添加 */}
        <div className="flex flex-col gap-2 mb-3 mt-3">
          <Input
            placeholder={t('common.search') || '搜索'}
            prefix={<SearchOutlined />}
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            size="small"
          />
          <div>
            <Button
              type="link"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => setShowAddLabel(true)}
            >
              {t('datasets.addLabel') || '添加标签'}
            </Button>
            {showAddLabel && (
              <Input
                size="small"
                placeholder={t('datasets.pressEnterToAdd') || '按Enter添加'}
                onPressEnter={handleAddLabel}
                onBlur={() => setShowAddLabel(false)}
                autoFocus
              />
            )}
          </div>
        </div>

        {/* 标签列表 */}
        <div className="overflow-y-auto" style={{ maxHeight: '400px' }}>
          <div className="space-y-2">
            {filteredLabels.map((label) => (
              <div
                key={label.id}
                className="flex justify-between items-center px-3 py-2 border border-gray-200 rounded cursor-pointer hover:bg-blue-50 hover:border-blue-400 transition-all"
              >
                <div className="flex items-center gap-2 flex-1">
                  <div
                    className="w-4 h-4 rounded"
                    style={{ backgroundColor: label.color }}
                  />
                  <span className="text-sm">{label.name}</span>
                </div>
                <MinusCircleOutlined
                  className="text-red-600 text-sm"
                  onClick={(e) => handleDeleteLabel(e, label.id)}
                />
              </div>
            ))}
          </div>
        </div>
      </Modal>

    </div>
  )
};

export default ObjectDetection;