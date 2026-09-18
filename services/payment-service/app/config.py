from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "payment-service"
    kafka_bootstrap_servers: str = "kafka-kafka-bootstrap.kafka:9092"
    postgres_dsn: str = "postgresql+asyncpg://staybook@postgres.data:5432/staybook"

settings = Settings()
