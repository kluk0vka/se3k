from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "notification-service"
    kafka_bootstrap_servers: str = "kafka-kafka-bootstrap.kafka:9092"
    mongo_host: str = "mongo.data"
    mongo_port: int = 27017
    mongo_user: str = "notification"
    mongo_password: str = ""
    mongo_db: str = "notifications"
    retention_days: int = 90

    @property
    def mongo_uri(self) -> str:
        return (
            f"mongodb://{self.mongo_user}:{self.mongo_password}@{self.mongo_host}:{self.mongo_port}/"
            f"{self.mongo_db}?authSource={self.mongo_db}"
        )


settings = Settings()
