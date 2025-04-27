// 尝试扩展声明
declare module "react-file-viewer" {
  interface Props {
    fileType: string; // 文件类型，例如 pdf、txt 等
    filePath: string; // 文件路径
    onError?: (e: Error) => void; // 错误处理函数
  }

  const FileViewer: React.FC<Props>; // 声明 FileViewer 是一个 React 组件
  export default FileViewer;
}
