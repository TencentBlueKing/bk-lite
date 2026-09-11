import { useEffect, useState } from 'react';
import type { UploadFile } from 'antd/es/upload/interface';

interface ImageBlobPreviewProps {
  file: UploadFile;
}

const ImageBlobPreview = ({ file }: ImageBlobPreviewProps) => {
  const [previewUrl, setPreviewUrl] = useState('');

  useEffect(() => {
    const source = file.originFileObj;
    if (!source || typeof URL.createObjectURL !== 'function') {
      setPreviewUrl('');
      return;
    }

    const objectUrl = URL.createObjectURL(source);
    setPreviewUrl(objectUrl);

    return () => {
      URL.revokeObjectURL(objectUrl);
    };
  }, [file.originFileObj]);

  if (!previewUrl) {
    return null;
  }

  return (
    <img
      src={previewUrl}
      alt={file.name}
      className="w-14 h-14 object-cover"
    />
  );
};

export default ImageBlobPreview;
