import json
import os

import requests
from dotenv import load_dotenv
from loguru import logger


def test_vllm_reranker():
    headers = {
        "accept": "application/json", "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('TEST_INFERENCE_TOKEN')}"
    }
    data = {
        "model": "bce-reranker-base_v1",
        "query": "What is the capital of France?",
        "documents": [
            "The capital of Brazil is Brasilia.",
            "The capital of France is Paris.", "Horses and cows are both animals"
        ]
    }
    response = requests.post(
        f"{os.getenv('TEST_INFERENCE_BASE_URL')}/rerank", headers=headers, json=data)
    logger.info(json.dumps(response.json(), indent=2))
