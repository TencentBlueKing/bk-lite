import os

from config.components.base import BASE_DIR, DEBUG

ROOT_URLCONF = "urls"

# 模板页面配置
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": (os.path.join(BASE_DIR, "templates"),),
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.web_env.custom_settings",
            ],
        },
    }
]

INSTALLED_APPS = (
    "apps.base",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_minio_backend",
    "django_filters",
    "mptt",
    "django_comment_migrate",
    "apps.core",
    "nats_client",
    "django_extensions",
)

SHELL_PLUS = "ipython"
IPYTHON_KERNEL_DISPLAY_NAME = "BK-Lite"

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

AUTHENTICATION_BACKENDS = (
    "apps.core.backends.AuthBackend",  # this is default
    "apps.core.backends.APISecretAuthBackend",
    "django.contrib.auth.backends.ModelBackend",
)

AUTH_USER_MODEL = "base.User"

MIDDLEWARE = (
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # 跨域检测中间件， 默认关闭
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # django国际化中间件
    "django.middleware.locale.LocaleMiddleware",
    "apps.core.middlewares.app_exception_middleware.AppExceptionMiddleware",
    "apps.core.middlewares.drf_middleware.DisableCSRFMiddleware",
    "apps.core.middlewares.api_middleware.APISecretMiddleware",
    "apps.core.middlewares.auth_middleware.AuthMiddleware",
    "better_exceptions.integrations.django.BetterExceptionsMiddleware",
)

if DEBUG:
    INSTALLED_APPS += (
        "corsheaders",
        "debug_toolbar",
    )  # noqa
    # 该跨域中间件需要放在前面
    MIDDLEWARE = (
        "corsheaders.middleware.CorsMiddleware",
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    ) + MIDDLEWARE  # noqa
    CORS_ORIGIN_ALLOW_ALL = True
    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOW_HEADERS = [
        "accept",
        "authorization",
        "content-type",
        "user-agent",
        "x-csrftoken",
        "x-requested-with",
        "api-authorization",
        "debug",
    ]

# 获取 apps 目录下的所有子目录名称
APPS_DIR = os.path.join(BASE_DIR, "apps")
if os.path.exists(APPS_DIR):
    install_apps = os.getenv("INSTALL_APPS", "")
    if install_apps:
        app_folders = [name for name in os.listdir(APPS_DIR) if os.path.isdir(os.path.join(APPS_DIR, name)) and name in install_apps.split(",")]
    else:
        exclude_apps = ["base", "core", "rpc"]
        app_folders = [
            name
            for name in os.listdir(APPS_DIR)
            if os.path.isdir(os.path.join(APPS_DIR, name)) and name not in exclude_apps and not name.startswith("_") and not name.startswith(".")
        ]

else:
    app_folders = []

INSTALLED_APPS += tuple(f"apps.{app}" for app in app_folders)

# 文件上传数量限制
DATA_UPLOAD_MAX_NUMBER_FILES = 100
