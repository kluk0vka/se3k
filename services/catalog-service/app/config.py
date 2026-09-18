from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "catalog-service"
    kafka_bootstrap_servers: str = "kafka-kafka-bootstrap.kafka:9092"
    mongo_host: str = "mongo.data"
    mongo_port: int = 27017
    mongo_user: str = "catalog"
    mongo_password: str = ""
    mongo_db: str = "catalog"
    valkey_host: str = "valkey.data"
    valkey_port: int = 6379
    valkey_password: str = ""
    inventory_url: str = "http://inventory-service.staybook.svc.cluster.local:8000"
    inventory_timeout_s: float = 1.0
    search_cache_ttl_s: int = 60
    degraded_cache_ttl_s: int = 5

    @property
    def mongo_uri(self) -> str:
        return (
            f"mongodb://{self.mongo_user}:{self.mongo_password}@{self.mongo_host}:{self.mongo_port}/"
            f"{self.mongo_db}?authSource={self.mongo_db}"
        )


settings = Settings()
