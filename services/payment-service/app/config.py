from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "payment-service"
    kafka_bootstrap_servers: str = "kafka-kafka-bootstrap.kafka:9092"
    postgres_host: str = "postgres.data"
    postgres_port: int = 5432
    postgres_user: str = "payment"
    postgres_password: str = ""
    postgres_db: str = "payment"
    psp_decline_rate: float = 0.05
    psp_latency_min_ms: int = 20
    psp_latency_max_ms: int = 80

    @property
    def dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
