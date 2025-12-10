from django.utils.crypto import get_random_string

REDIS_PASSWORD = get_random_string(32)
POSTGRES_PASSWORD = get_random_string(32)
MINIO_PASSWORD = get_random_string(32)
ELASTICSEARCH_PASSWORD = get_random_string(32)
CODE_SERVER_PASSWORD = get_random_string(32)
JUPYTER_TOKEN = get_random_string(32)

INIT_IMAGES = [
  {
    "name": "redis",
    "version": "5.0.14",
    "image_type": "infra",
    "image": "null",
    "default_port": 6379,
    "default_command": ["redis-server"],
    "default_args": ["--requirepass", REDIS_PASSWORD],
    "default_env": {},
    "expose_ports": [],
    "volume_mounts": [
      {
        "container_path": "/data"
      }
    ],
    
  },
  {
    "name": "postgres",
    "version": "15",
    "image_type": "infra",
    "image": "null",
    "default_port": 5432,
    "default_command": [],
    "default_args": [],
    "default_env": {
      "PGDATA": "/data/postgres",
      "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
      "POSTGRES_USER": "postgres"
    },
    "expose_ports": [],
    "volume_mounts": [
      {
        "container_path": "/data/postgres"
      }
    ],
  },
  {
    "name": "minio/minio",
    "version": "RELEASE.2024-05-01T01-11-10Z-cpuv1",
    "image_type": "infra",
    "image": "null",
    "default_port": 9000,
    "default_command": ["server"],
    "default_args": ["/data", "--console-address", ":9001"],
    "default_env": {
      "MINIO_ROOT_PASSWORD": MINIO_PASSWORD,
      "MINIO_ROOT_USER": "minio"
    },
    "expose_ports": [],
    "volume_mounts": [
      {
        "container_path": "/data"
      }
    ],
  },
  {
    "name": "bklite/mlflow",
    "version": "latest",
    "image_type": "infra",
    "image": "null",
    "default_port": 15000,
    "default_command": [
      "mlflow", 
      "server", 
      "--host", 
      "0.0.0.0", 
      "--port", 
      "15000", 
      "--backend-store-uri",
      f"postgresql+psycopg2://postgres:{POSTGRES_PASSWORD}@postgres:5432/mlflow",
      "--artifacts-destination",
      "s3://mlflow-artifacts/",
      "--serve-artifacts"
    ],
    "default_args": [],
    "default_env": {
      "AWS_ACCESS_KEY_ID": "minio",
      "AWS_SECRET_ACCESS_KEY": MINIO_PASSWORD,
      "AWS_DEFAULT_REGION": "us-east-1",
      "MLFLOW_S3_ENDPOINT_URL": "http://minio:9000"
    },
    "expose_ports": [],
    "volume_mounts": [],
  },
  {
    "name": "pgvector/pgvector",
    "version": "pg15",
    "image_type": "infra",
    "image": "null",
    "default_port": 5432,
    "default_command": ["postgres", "-c", "shared_preload_libraries=vector"],
    "default_args": [],
    "default_env": {
      "POSTGRES_USER": "postgres",
      "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
      "POSTGRES_DB": "vector_db",
      "PGDATA": "/var/lib/postgresql/data/pgdata"
    },
    "expose_ports": [],
    "volume_mounts": [
      {
        "container_path": "/var/lib/postgresql/data"
      }
    ],
  },
  {
    "name": "elasticsearch",
    "version": "8.11.0",
    "image_type": "infra",
    "image": "null",
    "default_port": 9200,
    "default_command": [],
    "default_args": [],
    "default_env": {
      "discovery.type": "single-node",
      "ELASTIC_PASSWORD": ELASTICSEARCH_PASSWORD,
      "xpack.security.enabled": "true",
      "xpack.security.http.ssl.enabled": "false",
      "xpack.security.transport.ssl.enabled": "false",
      "ES_JAVA_OPTS": "-Xms512m -Xmx512m"
    },
    "expose_ports": [],
    "volume_mounts": [
      {
        "container_path": "/usr/share/elasticsearch/data"
      }
    ],
  },
  {
    "name": "codercom/code-server",
    "version": "latest",
    "image_type": "ide",
    "image": "null",
    "default_port": 8081,
    "default_command": [],
    "default_args": [],
    "default_env": {
      "PASSWORD": CODE_SERVER_PASSWORD,
      "SUDO_PASSWORD": CODE_SERVER_PASSWORD,
      "DEFAULT_WORKSPACE": "/home/coder/project"
    },
    "expose_ports": [],
    "volume_mounts": [
      {
        "container_path": "/home/coder/project"
      }
    ],
  },
  {
    "name": "jupyter/scipy-notebook",
    "version": "latest",
    "image_type": "ide",
    "image": "null",
    "default_port": 8888,
    "default_command": ["start-notebook.sh"],
    "default_args": [],
    "default_env": {
      "JUPYTER_ENABLE_LAB": "yes",
      "JUPYTER_TOKEN": JUPYTER_TOKEN,
      "GRANT_SUDO": "yes",
      "CHOWN_HOME": "yes",
      "CHOWN_HOME_OPTS": "-R"
    },
    "expose_ports": [],
    "volume_mounts": [
      {
        "container_path": "/home/jovyan/work"
      }
    ],
  },
  {
    "name": "jupyter/tensorflow-notebook",
    "version": "latest",
    "image_type": "ide",
    "image": "null",
    "default_port": 8889,
    "default_command": ["start-notebook.sh"],
    "default_args": [],
    "default_env": {
      "JUPYTER_ENABLE_LAB": "yes",
      "JUPYTER_TOKEN": JUPYTER_TOKEN,
      "GRANT_SUDO": "yes"
    },
    "expose_ports": [],
    "volume_mounts": [
      {
        "container_path": "/home/jovyan/work"
      }
    ],
  },
  # {
  #   "name": "jupyter/pytorch-notebook",
  #   "version": "latest",
  #   "image_type": "ide",
  #   "image": "null",
  #   "default_port": 8888,
  #   "default_command": ["start-notebook.sh"],
  #   "default_args": [],
  #   "default_env": {
  #     "JUPYTER_ENABLE_LAB": "yes",
  #     "JUPYTER_TOKEN": JUPYTER_TOKEN,
  #     "GRANT_SUDO": "yes"
  #   },
  #   "expose_ports": [8888],
  #   "volume_mounts": [
  #     {
  #       "container_path": "/home/jovyan/work"
  #     }
  #   ],
  # },
]