import React from 'react';
import { WC } from '../chrome';

interface ImagePreviewProps {
  src: string;
  alt: string;
  onClose: () => void;
}

export const ImagePreview: React.FC<ImagePreviewProps> = ({ src, alt, onClose }) => {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: WC.overlay }}
      onClick={onClose}
    >
      <div className="relative max-h-[90vh] max-w-[90vw]">
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-2xl font-bold"
          style={{ color: WC.onPrimary }}
        >
          ✕
        </button>
        <img
          src={src}
          alt={alt}
          className="max-w-full max-h-[90vh] object-contain"
          onClick={(e) => e.stopPropagation()}
        />
      </div>
    </div>
  );
};
