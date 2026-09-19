ARG STRIMZI_KAFKA_IMAGE=quay.io/strimzi/kafka:1.2.0-kafka-4.3.1

FROM alpine:3.22 AS plugins
ARG AIVEN_S3_VERSION=3.4.3
ARG AIVEN_S3_SHA256=85661c4d3d49b85f4a65170a5c27464e4359760aa7140a24628e45323b6d7329
RUN apk add --no-cache curl \
 && curl -fsSL -o /tmp/s3.tar "https://github.com/Aiven-Open/cloud-storage-connectors-for-apache-kafka/releases/download/v${AIVEN_S3_VERSION}/s3-sink-connector-for-apache-kafka-${AIVEN_S3_VERSION}.tar" \
 && echo "${AIVEN_S3_SHA256}  /tmp/s3.tar" | sha256sum -c - \
 && mkdir -p /plugins/aiven-s3-sink \
 && tar -xf /tmp/s3.tar -C /plugins/aiven-s3-sink

FROM ${STRIMZI_KAFKA_IMAGE}
COPY --from=plugins /plugins /opt/kafka/plugins
USER 1001
