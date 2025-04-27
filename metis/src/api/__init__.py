from sanic import Blueprint

from src.api.agent_api import agent_api_router
from src.api.rag_api import rag_api_router

BLUEPRINTS = [agent_api_router, rag_api_router]

api = Blueprint.group(*BLUEPRINTS, url_prefix="/api")
