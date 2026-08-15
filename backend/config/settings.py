from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    llm_model: str = Field("claude-sonnet-5", env="LLM_MODEL")
    llm_max_tokens: int = Field(4096, env="LLM_MAX_TOKENS")

    # Qdrant
    qdrant_host: str = Field("localhost", env="QDRANT_HOST")
    qdrant_port: int = Field(6333, env="QDRANT_PORT")
    collection_name: str = Field("data_contracts", env="COLLECTION_NAME")
    retrieval_top_k: int = Field(5, env="RETRIEVAL_TOP_K")

    # Embeddings
    embedding_model: str = Field("all-MiniLM-L6-v2", env="EMBEDDING_MODEL")
    embedding_dim: int = Field(384, env="EMBEDDING_DIM")

    # Chunking
    chunk_size: int = Field(1000, env="CHUNK_SIZE")
    chunk_overlap: int = Field(150, env="CHUNK_OVERLAP")

    # Graph
    max_contracts_to_check: int = Field(5, env="MAX_CONTRACTS_TO_CHECK")

    # API
    api_host: str = Field("0.0.0.0", env="API_HOST")
    api_port: int = Field(8000, env="API_PORT")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        env="CORS_ORIGINS",
    )

    # Paths
    contracts_dir: str = Field("./contracts", env="CONTRACTS_DIR")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
