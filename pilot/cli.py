import fire
import requests
import yaml
from core.server_settings import server_settings
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


class BootStrap(object):
    def get_bot_config_data(self):
        logger.info(f"获取Pilot[{server_settings.munchkin_bot_id}]配置信息....")

        credentials = {
            "socketio": {
                "user_message_evt": "user_uttered",
                "bot_message_evt": "bot_uttered",
                "session_persistence": False,
            },
        }

        response = requests.get(
            server_settings.munchkin_base_url + f"/bot_mgmt/bot/{server_settings.munchkin_bot_id}/get_detail/",
            headers={
                "Authorization": f"TOKEN {server_settings.munchkin_api_key}",
                "Content-Type": "application/json",
            },
            stream=True,
        )
        response.raise_for_status()

        result = response.json()
        for channel in result["channels"]:
            credentials.update(channel["channel_config"])

        with open("data/credentials.yml", "w", encoding="utf-8") as f:
            yaml.dump(credentials, f, allow_unicode=True)

        endpoints = {
            "action_endpoint": {
                "url": "http://localhost:5055/webhook",
            },
            "models": {
                "url": f"{server_settings.munchkin_base_url}/bot_mgmt/rasa_model_download/?bot_id={server_settings.munchkin_bot_id}",
                "wait_time_between_pulls": None,
            },
            "tracker_store": {
                "type": "SQL",
                "dialect": "sqlite",
                "url": "",
                "db": "tracker.db",
                "username": "",
                "password": "",
            },
            # 'event_broker': {
            #     'type': 'pika',
            #     'url': 'rabbitmq-service',
            #     'username': server_settings.rabbitmq_username,
            #     'password': server_settings.rabbitmq_password,
            #     'queues': [
            #         'pilot'
            #     ]
            # }
            "event_broker": {
                "url": server_settings.nats_url,
                "namespace": server_settings.nats_namespace,
                "type": "custom_broker.nats_broker.NATSEventBroker",
            },
        }
        with open("data/endpoints.yml", "w", encoding="utf-8") as f:
            yaml.dump(endpoints, f, allow_unicode=True)


if __name__ == "__main__":
    load_dotenv()
    fire.Fire(BootStrap)
