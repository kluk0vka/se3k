from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "inventory-service"
    kafka_bootstrap_servers: str = "kafka-kafka-bootstrap.kafka:9092"
    postgres_host: str = "postgres.data"
    postgres_port: int = 5432
    postgres_user: str = "inventory"
    postgres_password: str = ""
    postgres_db: str = "inventory"
    hold_ttl_s: int = 900
    sweep_interval_s: float = 30.0

    @property
    def dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
