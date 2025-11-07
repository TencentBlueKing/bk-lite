'use client'
import { CodeOutlined, SaveOutlined } from '@ant-design/icons';
import type { AnnotatorRef, ImageSample } from '@labelu/image-annotator-react';
import {
  Button,
  message,
  Modal,
  Spin,
  Typography
} from 'antd';
import { useCallback, useEffect, useMemo, useState, useRef, forwardRef } from 'react';
import { useSearchParams } from 'next/navigation';
import useMlopsManageApi from '@/app/mlops/api/manage';
import styles from './index.module.scss'
// import dynamic from 'next/dynamic';

// 使用动态导入并禁用SSR，避免Next.js的服务端渲染导致的状态问题
// const ImageAnnotator = dynamic(
//   () => import('@labelu/image-annotator-react').then(mod => mod.Annotator),
//   { 
//     ssr: false
//   }
// );


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

const ObjectDetection = () => {
  const annotatorRef = useRef<AnnotatorRef>(null);
  const searchParams = useSearchParams();
  const { getObjectDetectionTrainDataInfo, updateObjectDetectionTrainData } = useMlopsManageApi();
  const [config, setConfig] = useState<any>(null);
  const [samples, setSamples] = useState<ImageSample[]>([]);
  const [currentSample, setCurrentSample] = useState<ImageSample | null>(null);
  const [result, setResult] = useState<any>({});
  const [loading, setLoading] = useState<boolean>(false)
  const [resultOpen, setResultOpen] = useState<boolean>(false);
  const id = searchParams.get('id') || '';

  useEffect(() => {
    setConfig(defaultConfig);
  }, [])

  useEffect(() => {
    if (id) {
      getTrainDataInfo();
    }
  }, [id]);

  // 发生变化时更新samples的标注数据
  const updateSamples = (labels: any, currentSample: ImageSample | null) => {
    const isNull = labels instanceof Object && Object.keys(labels).length > 0;

    if (!isNull) return;
    const image_url = currentSample?.url;
    const newSamples = samples.map((item: any) => {
      if (item.url === image_url) {
        return {
          ...item,
          data: labels
        }
      }
      return item;
    });
    setSamples(newSamples);
  };

  const onLoad = (engine: any) => {
    // 清理可能遗留的 DOM 元素
    engine.container.querySelectorAll('div').forEach((div: any) => {
      div.remove();
    });


    const updateSampleData = (eventName: string) => {
      const current = annotatorRef.current?.getSample();

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

    engine.on('add', addHandler);
    engine.on('delete', deleteHandler);
    engine.on('change', changeHandler);
    engine.on('mouseup', mouseupHandler);

  };


  const showResult = useCallback(() => {
    const labels = annotatorRef.current?.getAnnotations();
    console.log(labels);
    setResult(() => ({
      ...labels
    }));

    setResultOpen(true);
  }, [samples]);

  const saveResult = async () => {
    setLoading(true);
    try {
      const image_label = samples.map((item: ImageSample) => {
        return {
          image_url: item.url,
          label: item.data
        }
      });

      await updateObjectDetectionTrainData(id, {
        meta_data: JSON.stringify({
          image_label
        })
      });
      getTrainDataInfo();
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
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
        <Button type='primary' icon={<CodeOutlined rev={undefined} />} onClick={showResult}>标注结果</Button>
        <Button type='primary' icon={<SaveOutlined rev={undefined} />} onClick={saveResult} />
        {/* <Button type='primary' icon={<SettingOutlined rev={undefined} />} onClick={() => { }} /> */}
      </div>
    )
  }, [showResult]);

  const getTrainDataInfo = async () => {
    setLoading(true);
    try {
      const data = await getObjectDetectionTrainDataInfo(id, true, true);
      const label_data = data.meta_data?.image_label || [];
      const _images = data.train_data?.map((item: any, index: number) => {
        const label = label_data.find((lab: any) => lab?.image_url === item.image_url);
        return {
          id: index,
          name: item.image_name || '',
          url: item.image_url || '',
          data: label?.label || {},
        };
      }) || [];

      setSamples(_images);
      if (_images.length > 0) {
        setCurrentSample(_images[0]);
      }
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

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
      <Modal
        title="标注结果"
        open={resultOpen}
        onOk={onOk}
        width={800}
        okText={"确定"}
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