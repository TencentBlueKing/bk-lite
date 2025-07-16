import pandas as pd
from langchain_core.documents import Document
import logging

logger = logging.getLogger(__name__)

class ExcelLoader():
    def __init__(self, path, mode='full'):
        self.path = path
        self.mode = mode

    def dataframe_to_excel_format_string(self, df):
        # Remove rows and columns where all values are NaN
        df = df.dropna(how='all').dropna(axis=1, how='all')

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

        excel_format_str = excel_format_str.replace('nan', '')
        # Step 5: Return the accumulated string
        return excel_format_str

    def title_row_struct_load(self):
        sheets = pd.read_excel(self.path, sheet_name=None)

        # 初始化一个空列表来存储结果
        result = []

        for sheet_name, df in sheets.items():
            logger.info(f"Excel文件[{self.path}]的Sheet[{sheet_name}]的首行将被解析为表头")

            # 遍历每一行
            for index, row in df.iterrows():
                # 初始化一个空字符串来存储这一行的结果
                row_result = ''

                # 遍历这一行的每一列
                for col_name, col_value in row.items():
                    # 将列名和列值拼接成一个字符串，然后添加到结果中
                    row_result += f'{sheet_name}  {col_name}: {col_value}  '

                # 将这一行的结果添加到总结果中
                result.append(Document(row_result.strip(), metadata={
                    "format": "table", "sheet": sheet_name}))

        # 返回结果
        return result

    def load(self):
        if self.mode == 'full':
            return self.load_full_content()
        elif self.mode == 'title_row_struct':
            return self.title_row_struct_load()
        else:
            raise ValueError(
                f"Unsupported mode: {self.mode}. Supported modes are 'full' and 'title_row_struct'.")

    def load_full_content(self):
        # 使用pandas读取excel文件的所有sheet
        sheets = pd.read_excel(self.path, sheet_name=None)

        # 初始化一个空列表来存储结果
        result = []

        for sheet_name, df in sheets.items():
            logger.info(f"Excel文件[{self.path}]的Sheet[{sheet_name}]的全内容将被解析")

            # 读取Excel 的全内容
            full_content = self.dataframe_to_excel_format_string(df)
            result.append(
                Document(f'{sheet_name} {full_content}', metadata={"format": "table", "sheet": sheet_name}))

        # 返回结果
        return result
