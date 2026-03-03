import logging
from sanic import Blueprint

from api.example import example_router
from api.collect import collect_router
from api.monitor import monitor_router
from api.health import health_router

logger = logging.getLogger(__name__)

BLUEPRINTS = [collect_router, example_router, monitor_router, health_router]
ENTERPRISE_BLUEPRINTS = []

try:
    from enterprise.api import ENTERPRISE_BLUEPRINTS as ent_blueprints

    ENTERPRISE_BLUEPRINTS = list(ent_blueprints)
    logger.info("Enterprise API loaded successfully")
except ImportError:
    logger.debug("Enterprise API not available, skipping")

api = Blueprint.group(*BLUEPRINTS, url_prefix="/api")
enterprise_api = (
    Blueprint.group(*ENTERPRISE_BLUEPRINTS, url_prefix="/api/enterprise")
    if ENTERPRISE_BLUEPRINTS
    else None
)
