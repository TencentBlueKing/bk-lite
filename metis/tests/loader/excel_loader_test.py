from loguru import logger

from src.loader.excel_loader import ExcelLoader


def test_excel_loader():
    loader = ExcelLoader('tests/assert/excel_loader.xlsx', mode='full')
    rs = loader.load()
    logger.info(rs)


def test_excel_loader_title_row_struct_load():
    loader = ExcelLoader(
        'tests/assert/excel_loader_title_chunk.xlsx', mode='title_row_struct')
    rs = loader.title_row_struct_load()
    logger.info(rs)
