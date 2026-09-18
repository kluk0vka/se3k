from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "booking-service"
    kafka_bootstrap_servers: str = "kafka-kafka-bootstrap.kafka:9092"
    postgres_host: str = "postgres.data"
    postgres_port: int = 5432
    postgres_user: str = "booking"
    postgres_password: str = ""
    postgres_db: str = "booking"
    outbox_poll_interval_s: float = 0.2
    outbox_batch_size: int = 100
    price_per_night_minor: int = 550000

    @property
    def dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
