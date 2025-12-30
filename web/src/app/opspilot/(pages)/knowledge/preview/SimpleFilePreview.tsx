import React from "react";

export interface SimpleFilePreviewProps {
  fileType: string;
  fileUrl: string;
  onError?: (e: Error) => void;
}

const SimpleFilePreview: React.FC<SimpleFilePreviewProps> = ({ fileType, fileUrl }) => {
  if (!fileType || !fileUrl) return null;

  const wrapperStyle: React.CSSProperties = { width: "100%", height: "100%" };

  if (fileType.includes("pdf")) {
    return (
      <div style={wrapperStyle}>
        <iframe
          src={fileUrl}
          style={{ width: "100%", height: "100%", border: 0 }}
          title="PDF Preview"
        />
      </div>
    );
  }
  if (fileType.startsWith("image/")) {
    return (
      <div style={wrapperStyle}>
        <img src={fileUrl} alt="preview" style={{ maxWidth: "100%", height: "100%", objectFit: "contain" }} />
      </div>
    );
  }
  if (fileType.startsWith("text/")) {
    return (
      <div style={wrapperStyle}>
        <iframe
          src={fileUrl}
          style={{ width: "100%", height: "100%", border: 0 }}
          title="Text Preview"
        />
      </div>
    );
  }
  // 其他类型直接下载
  return (
    <a href={fileUrl} download style={{ color: '#1890ff' }}>
      下载文件
    </a>
  );
};

export default SimpleFilePreview;
