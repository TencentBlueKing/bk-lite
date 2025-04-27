const createFileChunks = (
  file: File,
  chunkSize: number = 5 * 1024 * 1024
): Blob[] => {
  const chunks: Blob[] = [];
  let current = 0;

  while (current < file.size) {
    const chunk = file.slice(current, current + chunkSize);
    chunks.push(chunk);
    current += chunkSize;
  }

  return chunks;
};

const uploadChunk = (
  chunk: Blob,
  index: number,
  fileName: string
): Promise<boolean> => {
  return new Promise((resolve) => {
    const formData = new FormData();
    formData.append("chunk", chunk);
    formData.append("index", index.toString());
    formData.append("fileName", fileName);

    // 模拟块上传，实际应用中替换为实际上传请求
    setTimeout(() => {
      console.log(`Uploaded chunk ${index} of ${fileName}`);
      resolve(true);
    }, 500); // 模拟500ms延迟
  });
};

export const uploadChunks = async (
  file: File,
  onProgress: (progressEvent: ProgressEvent) => void
): Promise<Blob> => {
  const chunks = createFileChunks(file);
  for (let i = 0; i < chunks.length; i++) {
    await uploadChunk(chunks[i], i, file.name);
    // 更新上传进度
    const progressEvent = new ProgressEvent("progress", {
      lengthComputable: true,
      loaded: i + 1,
      total: chunks.length,
    });
    onProgress(progressEvent);
  }

  // 聚合所有块成为完整文件
  const blob = new Blob(chunks);
  return blob;
};
