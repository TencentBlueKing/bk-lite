'use client';

import React, { useState } from 'react';
import Image, { type ImageProps } from 'next/image';
import {
  DEFAULT_MODEL_ICON_URL,
  getModelIconUrl,
} from '@/app/cmdb/utils/modelIcon';

interface ModelIconProps extends Omit<ImageProps, 'src' | 'onError'> {
  icon?: string;
  modelId?: string;
}

interface ModelIconImageProps extends Omit<ModelIconProps, 'icon' | 'modelId'> {
  initialSrc: string;
}

const ModelIconImage = ({
  initialSrc,
  alt,
  style,
  ...props
}: ModelIconImageProps) => {
  const [src, setSrc] = useState(initialSrc);
  const [fallbackUnavailable, setFallbackUnavailable] = useState(false);

  return (
    <Image
      {...props}
      src={src}
      alt={alt}
      style={{
        ...style,
        visibility: fallbackUnavailable ? 'hidden' : style?.visibility,
      }}
      onError={() => {
        if (src !== DEFAULT_MODEL_ICON_URL) {
          setSrc(DEFAULT_MODEL_ICON_URL);
          return;
        }
        setFallbackUnavailable(true);
      }}
    />
  );
};

const ModelIcon = ({ icon, modelId, alt = '', ...props }: ModelIconProps) => {
  const initialSrc = getModelIconUrl({ icn: icon, model_id: modelId });

  return (
    <ModelIconImage
      key={initialSrc}
      {...props}
      initialSrc={initialSrc}
      alt={alt}
    />
  );
};

export default ModelIcon;
