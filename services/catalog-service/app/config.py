from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "catalog-service"
    kafka_bootstrap_servers: str = "kafka-kafka-bootstrap.kafka:9092"
    mongo_uri: str = "mongodb://mongo.data:27017"
    valkey_url: str = "redis://valkey.data:6379/0"

settings = Settings()
