'use client';
import React, { useState, useCallback } from 'react';
import Cropper, { Area } from 'react-easy-crop';
import { Slider, Toast } from 'antd-mobile';
import { CloseOutline, CheckOutline, CloseCircleOutline, UndoOutline } from 'antd-mobile-icons';

interface ImageCropperProps {
  image: string;
  onCropComplete: (croppedImage: string) => void;
  onCancel: () => void;
}

type ControlMode = 'rotation' | 'zoom' | null;

export default function ImageCropper({ image, onCropComplete, onCancel }: ImageCropperProps) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null);
  const [activeControl, setActiveControl] = useState<ControlMode>('zoom'); // 默认为缩放模式

  const onCropCompleteCallback = useCallback(
    (croppedArea: Area, croppedAreaPixels: Area) => {
      setCroppedAreaPixels(croppedAreaPixels);
    },
    []
  );

  const createImage = (url: string): Promise<HTMLImageElement> =>
    new Promise((resolve, reject) => {
      const image = new Image();
      image.addEventListener('load', () => resolve(image));
      image.addEventListener('error', (error) => reject(error));
      image.src = url;
    });

  const getCroppedImg = async (
    imageSrc: string,
    pixelCrop: Area,
    rotation = 0
  ): Promise<string> => {
    const image = await createImage(imageSrc);
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    if (!ctx) {
      throw new Error('无法获取 canvas context');
    }

    const maxSize = Math.max(image.width, image.height);
    const safeArea = 2 * ((maxSize / 2) * Math.sqrt(2));

    canvas.width = safeArea;
    canvas.height = safeArea;

    ctx.translate(safeArea / 2, safeArea / 2);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.translate(-safeArea / 2, -safeArea / 2);

    ctx.drawImage(
      image,
      safeArea / 2 - image.width * 0.5,
      safeArea / 2 - image.height * 0.5
    );

    const data = ctx.getImageData(0, 0, safeArea, safeArea);

    canvas.width = pixelCrop.width;
    canvas.height = pixelCrop.height;

    ctx.putImageData(
      data,
      0 - safeArea / 2 + image.width * 0.5 - pixelCrop.x,
      0 - safeArea / 2 + image.height * 0.5 - pixelCrop.y
    );

    return canvas.toDataURL('image/jpeg', 0.95);
  };

  const handleConfirm = async () => {
    if (!croppedAreaPixels) {
      Toast.show({
        content: '请先选择裁剪区域',
        icon: 'fail',
      });
      return;
    }

    try {
      const croppedImage = await getCroppedImg(image, croppedAreaPixels, rotation);
      onCropComplete(croppedImage);
    } catch (error) {
      console.error('图片裁剪失败:', error);
      Toast.show({
        content: '图片裁剪失败',
        icon: 'fail',
      });
    }
  };

  // 重置旋转角度
  const handleResetRotation = () => {
    setRotation(0);
  };

  // 旋转90度
  const handleRotate90 = () => {
    setRotation((prev) => (prev + 90) % 360);
  };

  // 切换控制模式 - 互斥切换,不能同时为空
  const toggleControl = (mode: ControlMode) => {
    if (mode && activeControl !== mode) {
      setActiveControl(mode);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black flex flex-col">
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-[var(--color-bg)]">
        <button
          onClick={onCancel}
          className="w-10 h-10 flex items-center justify-center text-[var(--color-text-1)] text-2xl"
        >
          <CloseOutline fontSize={28} />
        </button>
        <h1 className="text-[var(--color-text-1)] text-lg font-medium">裁剪</h1>
        <button
          onClick={handleConfirm}
          className="w-10 h-10 flex items-center justify-center text-[var(--color-text-1)] text-2xl"
        >
          <CheckOutline fontSize={28} />
        </button>
      </div>

      {/* 裁剪区域 */}
      <div className="relative flex-1">
        <Cropper
          image={image}
          crop={crop}
          zoom={zoom}
          rotation={rotation}
          aspect={1}
          objectFit="contain"
          onCropChange={setCrop}
          onCropComplete={onCropCompleteCallback}
          onZoomChange={activeControl === 'zoom' ? setZoom : undefined}
          onRotationChange={activeControl === 'rotation' ? setRotation : undefined}
        />
      </div>

      {/* 底部控制面板 */}
      <div className="bg-black pb-6">
        {/* 控制滑块区域 */}
        {activeControl && (
          <div className="px-6 py-4 bg-[rgba(255,255,255,0.05)]">
            {activeControl === 'rotation' && (
              <div>
                <div className="flex items-center justify-center mb-3">
                  <span className="text-white text-base">{rotation.toFixed(1)}°</span>
                </div>
                <div className="flex items-center gap-3">
                  {/* 重置按钮 */}
                  <button
                    onClick={handleResetRotation}
                    className="w-8 h-8 flex items-center justify-center text-white"
                  >
                    <CloseCircleOutline fontSize={20} />
                  </button>
                  {/* 旋转滑块 */}
                  <div className="flex-1">
                    <Slider
                      value={rotation < 0 ? 0 : rotation > 360 ? 360 : rotation}
                      min={0}
                      max={360}
                      step={1}
                      onChange={(value) => setRotation(value as number)}
                      style={{
                        '--fill-color': '#1890ff',
                      }}
                    />
                  </div>
                  {/* 90度旋转按钮 */}
                  <button
                    onClick={handleRotate90}
                    className="w-8 h-8 flex items-center justify-center text-white"
                  >
                    <UndoOutline fontSize={20} />
                  </button>
                </div>
              </div>
            )}
            {activeControl === 'zoom' && (
              <div>
                <div className="flex items-center justify-center mb-3">
                  <span className="text-white text-base">{Math.round(zoom * 100)}%</span>
                </div>
                <div className="px-4">
                  <Slider
                    value={zoom}
                    min={1}
                    max={3}
                    step={0.1}
                    onChange={(value) => setZoom(value as number)}
                    style={{
                      '--fill-color': '#1890ff',
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* 功能按钮区 */}
        <div className="flex justify-around px-6">
          <button
            onClick={() => toggleControl('rotation')}
            className="flex flex-col items-center"
          >
            <div className={`iconfont icon-xuanzhuantupian w-12 h-12 text-3xl ${activeControl === 'rotation' ? 'text-blue-500' : 'text-white'}`}></div>
            <span className="text-white text-sm">旋转</span>
          </button>
          <button
            onClick={() => toggleControl('zoom')}
            className="flex flex-col items-center"
          >
            <div className={`iconfont icon-suofang w-12 h-12 text-3xl ${activeControl === 'zoom' ? 'text-blue-500' : 'text-white'}`}></div>
            <span className="text-white text-sm">缩放</span>
          </button>
        </div>
      </div>
    </div>
  );
}
