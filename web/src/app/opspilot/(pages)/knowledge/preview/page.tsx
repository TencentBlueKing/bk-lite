"use client";
import React, { useEffect, useState, useRef } from "react";
import dynamic from "next/dynamic";
import { Alert, Spin } from "antd";
import { useAuth } from "@/context/auth";
import { useSearchParams } from "next/navigation";
import { remark } from "remark";
import html from "remark-html";
import gfm from "remark-gfm";
import "github-markdown-css/github-markdown.css";
const FileViewer = dynamic(() => import("react-file-viewer"), {
  ssr: false,
});
import * as docx from "docx-preview";
import ExcelJS from "exceljs";
import { sanitizeHtml } from "@/utils/sanitize";

const extractFilename = (contentDisposition: string | null): string | null => {
  if (!contentDisposition) return null;

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }

  const asciiMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return asciiMatch?.[1] ?? null;
};

const getFileExtension = (fileName: string | null): string | null => {
  if (!fileName || !fileName.includes(".")) return null;
  return fileName.split(".").pop()?.toLowerCase() ?? null;
};

const isMarkdownFile = (contentType: string | null, fileName: string | null): boolean => {
  const extension = getFileExtension(fileName);
  return contentType?.includes("text/markdown") === true || extension === "md" || extension === "markdown";
};

const isWordFile = (contentType: string | null, fileName: string | null): boolean => {
  const extension = getFileExtension(fileName);
  return contentType?.includes("wordprocessingml.document") === true || extension === "docx";
};

const isSpreadsheetFile = (contentType: string | null, fileName: string | null): boolean => {
  const extension = getFileExtension(fileName);
  return contentType?.includes("spreadsheetml.sheet") === true || extension === "xlsx";
};

const getFileTypeForViewer = (contentType: string | null, fileName: string | null): string | null => {
  const extension = getFileExtension(fileName);
  const typeByExtension: Record<string, string> = {
    pdf: "pdf",
    txt: "txt",
    text: "txt",
    csv: "csv",
    png: "png",
    jpg: "jpg",
    jpeg: "jpg",
  };

  if (extension && typeByExtension[extension]) {
    return typeByExtension[extension];
  }

  if (!contentType) return null;

  const typeByContentType: Record<string, string> = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/csv": "csv",
    "image/png": "png",
    "image/jpeg": "jpg",
  };

  return Object.entries(typeByContentType).find(([key]) => contentType.includes(key))?.[1] || null;
};

const PreviewPage: React.FC = () => {
  const searchParams = useSearchParams();
  const id = searchParams?.get("id") || null;
  const authContext = useAuth();
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [fileType, setFileType] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [markdownHtml, setMarkdownHtml] = useState<string>("");
  const [viewerType, setViewerType] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const docxContainerRef = useRef<HTMLDivElement>(null);
  const xlsxContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let objectUrl: string | null = null;

    const fetchFile = async () => {
      setLoading(true);
      setFileUrl(null);
      setFileType(null);
      setFileName(null);
      setMarkdownHtml("");
      setViewerType(null);

      if (!id) {
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`/opspilot/api/docFile?id=${id}`, {
          headers: { Authorization: `Bearer ${authContext?.token}` },
        });

        if (!response.ok) throw new Error("Failed to fetch file");

        const contentDisposition = response.headers.get("Content-Disposition");
        const blob = await response.blob();
        const contentType = response.headers.get("Content-Type") || blob.type || null;
        const resolvedFileName = extractFilename(contentDisposition);

        setFileName(resolvedFileName);
        setFileType(contentType);

        if (isMarkdownFile(contentType, resolvedFileName)) {
          const rawMarkdown = await blob.text();
          const processedContent = await remark().use(gfm).use(html).process(rawMarkdown);
          setMarkdownHtml(sanitizeHtml(processedContent.toString()));
          setFileUrl(null);
          setViewerType(null);
          setLoading(false);
          return;
        }

        objectUrl = URL.createObjectURL(blob);
        setMarkdownHtml("");
        setFileUrl(objectUrl);
        setViewerType(getFileTypeForViewer(contentType, resolvedFileName));
        setFileType(contentType);

        setLoading(false);
      } catch (error) {
        console.error("Error:", error);
        setLoading(false);
        setViewerType(null);
      }
    };

    fetchFile();
    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [authContext?.token, id]);

  useEffect(() => {
    if (isWordFile(fileType, fileName) && fileUrl) {
      if (typeof window !== "undefined" && docxContainerRef.current) {
        const renderDocx = async () => {
          const response = await fetch(fileUrl!);
          const arrayBuffer = await (await response.blob()).arrayBuffer();
          docx.renderAsync(arrayBuffer, docxContainerRef.current!);
        };
        renderDocx();
      }
    }
  }, [fileName, fileType, fileUrl]);

  useEffect(() => {
    if (isSpreadsheetFile(fileType, fileName) && fileUrl && xlsxContainerRef.current) {
      const renderExcel = async () => {
        try {
          const response = await fetch(fileUrl);
          const arrayBuffer = await response.arrayBuffer();
          const workbook = new ExcelJS.Workbook();
          await workbook.xlsx.load(arrayBuffer);
          const worksheet = workbook.worksheets[0];

          // 使用 DOM API + textContent 构建表格，绝不把单元格内容拼成 HTML 字符串注入，
          // 避免 XLSX 单元格中的恶意标记导致存储型 XSS。
          const table = document.createElement("table");
          table.style.borderCollapse = "collapse";
          table.style.width = "100%";

          worksheet.eachRow({ includeEmpty: true }, (row, rowNumber) => {
            const tr = document.createElement("tr");
            row.eachCell({ includeEmpty: true }, (cell) => {
              const cellValue = cell.value?.toString() || '';
              const td = document.createElement(rowNumber === 1 ? "th" : "td");
              // 关键：使用 textContent，单元格内容仅作为纯文本展示。
              td.textContent = cellValue;
              td.style.border = "1px solid #ccc";
              td.style.padding = "4px 8px";
              tr.appendChild(td);
            });
            table.appendChild(tr);
          });

          if (xlsxContainerRef?.current) {
            xlsxContainerRef.current.replaceChildren(table);
          }
        } catch (error) {
          console.error("Excel render failed:", error);
        }
      };

      renderExcel();
    }
  }, [fileName, fileType, fileUrl]);

  if (loading) {
    return (
      <div className="w-full h-full flex justify-center items-center">
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="w-full h-full">
      {markdownHtml && (
        <div className="markdown-body mx-auto max-w-5xl px-6 py-8" dangerouslySetInnerHTML={{ __html: markdownHtml }} />
      )}

      {isWordFile(fileType, fileName) && fileUrl && (
        <div ref={docxContainerRef} className="w-full h-full" />
      )}

      {isSpreadsheetFile(fileType, fileName) && fileUrl && (
        <div ref={xlsxContainerRef} className="w-full h-full overflow-auto" />
      )}

      {!markdownHtml && !isWordFile(fileType, fileName) && !isSpreadsheetFile(fileType, fileName) && fileUrl && viewerType && (
        <FileViewer
          fileType={viewerType}
          filePath={fileUrl}
          onError={(e: Error) => console.error("FileViewer error:", e)}
        />
      )}

      {!markdownHtml && !isWordFile(fileType, fileName) && !isSpreadsheetFile(fileType, fileName) && !viewerType && !loading && (
        <div className="mx-auto max-w-3xl px-6 py-8">
          <Alert
            type="warning"
            showIcon
            message="当前文件暂不支持在线预览"
            description={fileName ? `文件名: ${fileName}` : "未识别到可预览的文件类型。"}
          />
        </div>
      )}
    </div>
  );
};

export default PreviewPage;
