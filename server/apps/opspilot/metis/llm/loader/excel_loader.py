import pandas as pd
from langchain_core.documents import Document
from loguru import logger


class ExcelLoader:
    def __init__(self, path, mode="full"):
        self.path = path
        self.mode = mode

    def _safe_read_excel(self, sheet_name=None):
        """安全读取Excel文件，带有多种降级策略

        Args:
            sheet_name: sheet名称，None表示读取所有sheet

        Returns:
            dict: sheet_name -> DataFrame 的字典
        """
        strategies = [
            # 策略1：使用 openpyxl 引擎，忽略样式（最快）
            {"engine": "openpyxl", "engine_kwargs": {"data_only": True, "read_only": True}},
            # 策略2：使用 openpyxl 引擎，默认参数
            {"engine": "openpyxl"},
        ]

        last_error = None

        for i, strategy in enumerate(strategies, 1):
            try:
                logger.info(f"尝试策略 {i}/{len(strategies)} 读取 Excel 文件: {self.path}, 引擎: {strategy.get('engine')}")
                sheets = pd.read_excel(self.path, sheet_name=sheet_name, **strategy)
                logger.info(f"成功使用策略 {i} 读取 Excel 文件")
                return sheets
            except Exception as e:
                last_error = e
                logger.warning(f"策略 {i} 失败: {type(e).__name__}: {str(e)[:100]}")
                continue

        # 所有策略都失败，抛出最后一个错误
        error_msg = f"所有读取策略均失败，文件: {self.path}. 最后错误: {type(last_error).__name__}: {str(last_error)}"
        logger.error(error_msg)
        raise ValueError(error_msg) from last_error

    def dataframe_to_excel_format_string(self, df):
        # Remove rows and columns where all values are NaN
        df = df.dropna(how="all").dropna(axis=1, how="all")

        # Step 1: Initialize an empty string for the formatted content
        excel_format_str = ""

        # Step 2: Format and append column headers
        column_headers = "\t".join(str(df.columns))  # Using tab as a separator
        excel_format_str += column_headers + "\n"

        # Step 3 & 4: Iterate through rows and append their formatted string representation
        for index, row in df.iterrows():
            # Convert all cell values to string to avoid any conversion issues
            row_str = "\t".join(row.astype(str))
            excel_format_str += row_str + "\n"

        excel_format_str = excel_format_str.replace("nan", "")
        # Step 5: Return the accumulated string
        return excel_format_str

    def title_row_struct_load(self):
        sheets = self._safe_read_excel(sheet_name=None)

        # 初始化一个空列表来存储结果
        result = []

        for sheet_name, df in sheets.items():
            logger.info(f"Excel文件[{self.path}]的Sheet[{sheet_name}]的首行将被解析为表头")

            # 遍历每一行
            for index, row in df.iterrows():
                # 初始化一个空字符串来存储这一行的结果
                row_result = ""

                # 遍历这一行的每一列
                for col_name, col_value in row.items():
                    # 将列名和列值拼接成一个字符串，然后添加到结果中
                    row_result += f"{sheet_name}  {col_name}: {col_value}  "

                # 将这一行的结果添加到总结果中
                result.append(Document(row_result.strip(), metadata={"format": "table", "sheet": sheet_name}))

        # 返回结果
        return result

    def excel_full_content_parse_load(self):
        # 使用pandas读取excel文件的所有sheet
        sheets = self._safe_read_excel(sheet_name=None)

        # 初始化一个空列表来存储结果
        result = []

        for sheet_name, df in sheets.items():
            logger.info(f"Excel文件[{self.path}]的Sheet[{sheet_name}]将被解析为单个Document")

            # 读取Excel Sheet的全内容
            full_content = self.dataframe_to_excel_format_string(df)
            result.append(Document(full_content, metadata={"format": "table", "sheet": sheet_name, "source": self.path}))

        # 返回结果
        return result

    def load(self):
        if self.mode == "full":
            return self.load_full_content()
        elif self.mode == "excel_header_row_parse":
            return self.title_row_struct_load()
        elif self.mode == "excel_full_content_parse":
            return self.excel_full_content_parse_load()
        else:
            raise ValueError(f"Unsupported mode: {self.mode}. Supported modes are 'full', 'excel_header_row_parse' and 'excel_full_content_parse'.")

    def load_full_content(self):
        # 使用pandas读取excel文件的所有sheet
        sheets = self._safe_read_excel(sheet_name=None)

        # 初始化一个空字符串来存储所有sheet的内容
        all_sheets_content = ""
        sheet_names = []

        for sheet_name, df in sheets.items():
            logger.info(f"Excel文件[{self.path}]的Sheet[{sheet_name}]的全内容将被解析")
            sheet_names.append(sheet_name)

            # 读取Excel Sheet的全内容
            sheet_content = self.dataframe_to_excel_format_string(df)
            all_sheets_content += f"{sheet_name}\n{sheet_content}\n\n"

        # 创建单个Document包含所有Sheet内容
        result = [Document(all_sheets_content.strip(), metadata={"format": "table", "sheets": sheet_names, "source": self.path})]

        # 返回结果
        return result
