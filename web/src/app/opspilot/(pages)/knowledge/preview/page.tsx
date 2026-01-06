"use client";
import React, { useEffect, useState, useRef } from "react";
import { Spin } from "antd";
import { useAuth } from "@/context/auth";
import { useSearchParams } from "next/navigation";
import * as docx from "docx-preview";
import ExcelJS from "exceljs";
import SimpleFilePreview from "./SimpleFilePreview";

const PreviewPage: React.FC = () => {
  const searchParams = useSearchParams();
  const id = searchParams?.get("id") || null;
  const authContext = useAuth();
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [fileType, setFileType] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const docxContainerRef = useRef<HTMLDivElement>(null);
  const xlsxContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchFile = async () => {
      if (!id) return;
      try {
        const response = await fetch(`/opspilot/api/docFile?id=${id}`, {
          headers: { Authorization: `Bearer ${authContext?.token}` },
        });

        if (!response.ok) throw new Error("Failed to fetch file");

        const contentType = response.headers.get("Content-Type");
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        setFileUrl(url);
        setFileType(contentType);
        setLoading(false);
      } catch (error) {
        console.error("Error:", error);
        setLoading(false);
      }
    };

    fetchFile();
    return () => {
      if (fileUrl) {
        URL.revokeObjectURL(fileUrl);
      }
    };
  }, [id]);

  useEffect(() => {
    if (fileType?.includes("wordprocessingml.document")) {
      if (typeof window !== "undefined" && docxContainerRef.current) {
        const renderDocx = async () => {
          const response = await fetch(fileUrl!);
          const arrayBuffer = await (await response.blob()).arrayBuffer();
          docx.renderAsync(arrayBuffer, docxContainerRef.current!);
        };
        renderDocx();
      }
    }
  }, [fileType, fileUrl]);

  useEffect(() => {
    if (fileType?.includes("spreadsheetml.sheet") && fileUrl && xlsxContainerRef.current) {
      const renderExcel = async () => {
        try {
          const response = await fetch(fileUrl);
          const arrayBuffer = await response.arrayBuffer();
          const workbook = new ExcelJS.Workbook();
          await workbook.xlsx.load(arrayBuffer);
          const worksheet = workbook.worksheets[0];
          let htmlStr = '<table>';
          worksheet.eachRow((row, rowNumber) => {
            htmlStr += '<tr>';
            row.eachCell({ includeEmpty: true }, (cell) => {
              const cellValue = cell.value?.toString() || '';
              htmlStr += rowNumber === 1 ? `<th>${cellValue}</th>` : `<td>${cellValue}</td>`;
            });
            htmlStr += '</tr>';
          })
          htmlStr += '</table>';

          if (xlsxContainerRef?.current) {
            xlsxContainerRef.current.innerHTML = htmlStr;
          }

          const table = xlsxContainerRef?.current?.querySelector("table");
          if (table) {
            table.style.borderCollapse = "collapse";
            table.style.width = "100%";
            const cells = table.querySelectorAll("td, th");
            cells.forEach((cell) => {
              if (cell instanceof HTMLElement) {
                cell.style.border = "1px solid #ccc";
                cell.style.padding = "4px 8px";
              }
            });
          }
        } catch (error) {
          console.error("Excel render failed:", error);
        }
      };

      renderExcel();
    }
  }, [fileType, fileUrl]);



  if (loading) {
    return (
      <div className="w-full h-full flex justify-center items-center">
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: "100vh" }}>
      {fileType?.includes("wordprocessingml.document") && (
        <div ref={docxContainerRef} style={{ width: "100%", height: "100%" }} />
      )}

      {fileType?.includes("spreadsheetml.sheet") && (
        <div ref={xlsxContainerRef} style={{ width: "100%", height: "100%", overflow: "auto" }} />
      )}

      {/* 其他类型用自定义预览组件 */}
      {!fileType?.includes("wordprocessingml.document") && !fileType?.includes("spreadsheetml.sheet") && fileUrl && fileType && (
        <SimpleFilePreview fileType={fileType} fileUrl={fileUrl} onError={(e) => console.error("FilePreview error:", e)} />
      )}
    </div>
  );
};

export default PreviewPage;
