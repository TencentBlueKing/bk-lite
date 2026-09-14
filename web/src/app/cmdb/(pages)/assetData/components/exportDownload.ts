export const downloadBlobFile = (blob: Blob, filename: string) => {
  const link = document.createElement('a');
  const objectUrl = URL.createObjectURL(blob);

  try {
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
  } finally {
    try {
      try {
        link.remove();
      } catch (removeError) {
        link.parentNode?.removeChild(link);
        throw removeError;
      }
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  }
};
