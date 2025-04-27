from langchain_huggingface import HuggingFaceEmbeddings


class EmbedBuilder:
    @staticmethod
    def get_embed(protocol: str):
        model_type = protocol.split(':')[1]
        model_name = protocol.split(':')[2]
        if model_type == 'huggingface_embedding':
            return  HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': False},
                cache_folder="./models"
            )
        else:
            raise ValueError(f"Unsupported model type: {model_type}")
