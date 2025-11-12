'use client'
import { CodeOutlined, SaveOutlined, EditOutlined, CloudUploadOutlined, ReloadOutlined } from '@ant-design/icons';
import type { AnnotatorRef, ImageSample } from '@labelu/image-annotator-react';
import {
  Button,
  message,
  Modal,
  Spin,
  Radio,
  type CheckboxOptionType,
  Typography,
  Tooltip
} from 'antd';
import { useCallback, useEffect, useMemo, useState, useRef, forwardRef, Dispatch, SetStateAction } from 'react';
import { useSearchParams } from 'next/navigation';
import useMlopsManageApi from '@/app/mlops/api/manage';
import styles from './index.module.scss'
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
const { confirm } = Modal;

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

interface ImageLabel {
  image_url: string;
  label: any;
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

const rectClassName = ['human', 'bicycle', 'traffic_sign', 'reactant', 'catalyst', 'product'];

const defaultConfig = {
  width: 800,
  height: 600,
  image: {
    url: "",
    rotate: 0
  },
  point: {
    maxPointAmount: 100,
    labels:
      [
        { color: '#1899fb', key: 'Knee', value: 'knee' },
        { color: '#6b18fb', key: 'Head', value: 'head' },
        { color: '#5cfb18', key: 'Hand', value: 'hand' },
        { color: '#fb8d18', key: 'Elbow', value: 'elbow' },
        { color: '#fb187e', key: 'Foot', value: 'foot' }
      ]
  },
  line: {
    lineType: 'line',
    minPointAmount: 2,
    maxPointAmount: 100,
    edgeAdsorptive: false,
    labels: [{ color: '#ff0000', key: 'Lane', value: 'lane' }],
  },
  rect: {
    minWidth: 1,
    minHeight: 1,
    labels: [
      { color: '#03ba18ba', key: 'Human', value: 'human' },
      { color: '#ff00ff', key: 'Bicycle', value: 'bicycle' },
      { color: '#2e5fff', key: 'Traffic-sign', value: 'traffic_sign' },
      { color: '#662eff', key: 'Reactant', value: 'reactant' },
      { color: '#ffb62e', key: 'Catalyst', value: 'catalyst' },
      { color: '#ff2ea4', key: 'Product', value: 'product' },
    ]
  },
  polygon: {
    lineType: 'line',
    minPointAmount: 2,
    maxPointAmount: 100,
    edgeAdsorptive: false,
    labels: [{ color: '#8400ff', key: 'House', value: 'house' }],
  },
  relation: {
    style: {
      lineStyle: 'dashed',
      arrowType: 'single',
    },
    labels: [{ color: '#741a2a', key: 'Hit', value: 'hit' }],
  },
  cuboid: {
    labels: [{ color: '#ff6d2e', key: 'Car', value: 'car' }],
  },
};

const ObjectDetection = ({
  isChange,
  setIsChange
}: {
  isChange: boolean;
  setIsChange: Dispatch<SetStateAction<boolean>>
}) => {
  const { t } = useTranslation();
  const annotatorRef = useRef<AnnotatorRef>(null);
  const searchParams = useSearchParams();
  const { getObjectDetectionTrainDataInfo, updateObjectDetectionTrainData, generateYoloDataset } = useMlopsManageApi();
  const [config, setConfig] = useState<any>(null);
  const [currentSample, setCurrentSample] = useState<ImageSample | null>(null);
  const [result, setResult] = useState<any>({});
  const [loading, setLoading] = useState<boolean>(false)
  const [resultOpen, setResultOpen] = useState<boolean>(false);
  const [tagOpen, setTagOpen] = useState<boolean>(false);
  const [casualType, setCasualType] = useState<string>('');
  const [trainData, setTrainData] = useState<ObjectDetectionTrainData[]>([]);
  const [metaData, setMetadata] = useState<{
    image_label: ImageLabel[];
    yolo_dataset_url: string;
    class_name: string[];
  }>({
    image_label: [],
    yolo_dataset_url: '',
    class_name: []
  })
  const id = searchParams.get('id') || '';

  useEffect(() => {
    setConfig(defaultConfig);
  }, [])

  useEffect(() => {
    if (id) {
      getTrainDataInfo();
    }
  }, [id]);

  useEffect(() => {
    const trainType = trainData.find((item: ObjectDetectionTrainData) => item.image_url === currentSample?.url);
    setCasualType(trainType?.type || '');
  }, [currentSample])

  const options: CheckboxOptionType[] = [
    { label: t(`datasets.train`), value: 'train' },
    { label: t(`datasets.validate`), value: 'val' },
    { label: t(`datasets.test`), value: 'test' },
  ];

  const samples = useMemo(() => {
    const label_data = metaData?.image_label || [];
    const _images = trainData?.map((item: ObjectDetectionTrainData, index: number) => {
      const label = label_data.find((lab: ImageLabel) => lab?.image_url === item.image_url);
      return {
        id: index,
        name: item.image_name || '',
        url: item.image_url || '',
        data: label?.label || {},
        type: item.type || ''
      };
    }) || [];

    if (!currentSample) setCurrentSample(_images[0])
    return _images;
  }, [trainData, metaData, casualType]);

  // 发生变化时更新samples的标注数据
  const updateSamples = (labels: any, currentSample: ImageSample | null) => {
    const isNull = labels instanceof Object && Object.keys(labels).length > 0;

    if (!isNull) return;
    const image_url = currentSample?.url;
    const newImageLabel = metaData.image_label.map((item: ImageLabel) => {
      if (item.image_url === image_url) {
        return {
          image_url: item.image_url || '',
          label: labels
        }
      }
      return item;
    });
    setMetadata((prev) => ({ ...prev, image_label: newImageLabel }));
  };

  const onLoad = (engine: any) => {
    // 清理可能遗留的 DOM 元素
    engine.container.querySelectorAll('div').forEach((div: any) => {
      div.remove();
    });


    const updateSampleData = (eventName: string) => {
      const current = annotatorRef.current?.getSample();
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
        if (current) {
          setCurrentSample(current);
        }
      } else {
        const labels = annotatorRef.current?.getAnnotations();
        if (current && (current?.url !== currentSample?.url)) {
          setCurrentSample(current);
          updateSamples(labels, current);
        } else {
          updateSamples(labels, currentSample)
        }
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

  const showResult = useCallback(() => {
    const labels = annotatorRef.current?.getAnnotations();
    setResult(() => ({
      ...labels
    }));

    setResultOpen(true);
  }, [samples]);

  const saveResult = async () => {
    setLoading(true);
    try {
      const params = {
        train_data: JSON.stringify(trainData),
        meta_data: JSON.stringify({
          ...metaData,
          class_name: rectClassName
        })
      }
      await updateObjectDetectionTrainData(id, params);
      setIsChange(false);
      getTrainDataInfo();
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  const onSelectChange = (event: any) => {
    setCasualType(event.target?.value || '');
  };

  const onSelectConfirm = () => {
    const _trainData = trainData.map((item: ObjectDetectionTrainData) => {
      if (item.image_url === currentSample?.url) {
        return {
          ...item,
          type: casualType || 'train'
        }
      }
      return item;
    });
    setTrainData((_trainData));
    setTagOpen(false);
  };

  const onSelectCancel = () => {
    setTagOpen(false);
    const trainType = trainData.find((item: ObjectDetectionTrainData) => item.image_url === currentSample?.url);
    setCasualType(trainType?.type || '');
  };

  const onError = useCallback((err: any) => {
    console.error('Error:', err);
    message.error(err.message);
  }, []);

  const onOk = () => {
    setResultOpen(false);
  };

  const requestEdit = useCallback(() => {
    // 允许其他所有编辑操作
    return true;
  }, []);

  const toolbarRight = useMemo(() => {
    return (
      <div className='flex items-center gap-2'>
        <Tooltip title={t('common.refresh')}>
          <Button type='default' icon={<ReloadOutlined rev={undefined} />} onClick={() => getTrainDataInfo()} />
        </Tooltip>
        <Tooltip title={t('datasets.generateTitle')}>
          <Button type='default' icon={<CloudUploadOutlined rev={undefined} />} onClick={() => generateDataset()} />
        </Tooltip>
        <Tooltip title={t('datasets.editImageType')}>
          <Button type='default' icon={<EditOutlined rev={undefined} />} onClick={() => setTagOpen(true)} />
        </Tooltip>
        <Tooltip title="展示标注结果">
          <Button type='default' icon={<CodeOutlined rev={undefined} />} onClick={showResult} />
        </Tooltip>
        <Tooltip title={t('datasets.saveChanges')}>
          <Button type='default' icon={<SaveOutlined rev={undefined} />} onClick={saveResult} />
        </Tooltip>
        {/* <Button type='primary' icon={<SettingOutlined rev={undefined} />} onClick={() => { }} /> */}
      </div>
    )
  }, [showResult, trainData]);

  const getTrainDataInfo = async () => {
    setLoading(true);
    try {
      const data = await getObjectDetectionTrainDataInfo(id, true, true);
      setTrainData(data.train_data);
      setMetadata(data.meta_data);
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  const generateDataset = async () => {
    setLoading(true);
    try {
      if (isChange) {
        confirm({
          title: t('datasets.generateTitle'),
          content: t('datasets.generateContent'),
          okText: t('common.confirm'),
          cancelText: t('common.cancel'),
          centered: true,
          onOk() {
            return new Promise(async (resolve) => {
              await generateYoloDataset(id);
              resolve(true);
            })
          }
        })
      } else {
        await generateYoloDataset(id);
      }
      message.success(t('common.success'));
    } catch (e) {
      console.log(e);
      message.error(t('common.error'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={`${styles.container}`}>
      <Spin className='w-full' spinning={loading}>
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
      <OperateModal
        open={tagOpen}
        title={t(`common.edit`)}
        onCancel={onSelectCancel}
        footer={[
          <Button key="submit" type="primary" onClick={onSelectConfirm}>
            {t('common.confirm')}
          </Button>,
          <Button key="cancel" onClick={onSelectCancel}>
            {t('common.cancel')}
          </Button>,
        ]}
      >
        <div className='h-[20px] leading-[20px]'>
          <span className='mr-2'>{t(`datasets.fileType`) + ':'}</span>
          <Radio.Group options={options} value={casualType} onChange={onSelectChange} />
        </div>
      </OperateModal>
      <Modal
        title="标注结果"
        open={resultOpen}
        onOk={onOk}
        width={800}
        okText={t('common.confirm')}
        onCancel={() => setResultOpen(false)}
      >
        <Typography>
          <pre>
            {JSON.stringify(result, null, 2)}
          </pre>
        </Typography>
      </Modal>
    </div>
  )
};

export default ObjectDetection;