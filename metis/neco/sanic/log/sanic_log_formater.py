from sanic.logging.formatter import AutoFormatter, LegacyFormatter, LegacyAccessFormatter, ProdAccessFormatter
from sanic.logging.color import Colors as c


class SanicLogFormatter(LegacyFormatter):
    PREFIX_FORMAT = "%(asctime)s [%(levelname)s] [%(filename)s:%(funcName)s:%(lineno)s] "


class SanicAccessFormatter(ProdAccessFormatter):
    pass
