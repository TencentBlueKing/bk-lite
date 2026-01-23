# 使用时区
USE_TZ = True

# 时区设置
# TIME_ZONE = "Asia/Shanghai"
TIME_ZONE = "UTC"

# 语言设置
LANGUAGE_CODE = "zh-CN"
# 国际化设置
USE_I18N = True
# 本地化设置
USE_L10N = True

# 定义支持的语言
LANGUAGES = (
    ("en", "English"),
    ("zh-CN", "简体中文"),
)


# 翻译文件目录（已迁移至 apps/*/language/*.yaml，使用 LanguageLoader）
# LOCALE_PATHS = (os.path.join(BASE_DIR, "locale"),)
