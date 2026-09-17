FROM bitnamilegacy/postgresql:15.9.0

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        make \
    && curl -fsSL -o /tmp/pg_cron.tar.gz \
        https://github.com/citusdata/pg_cron/archive/refs/tags/v1.6.4.tar.gz \
    && tar -xzf /tmp/pg_cron.tar.gz -C /tmp \
    && make -C /tmp/pg_cron-1.6.4 \
        PG_CONFIG=/opt/bitnami/postgresql/bin/pg_config \
    && make -C /tmp/pg_cron-1.6.4 install \
        PG_CONFIG=/opt/bitnami/postgresql/bin/pg_config \
    && rm -rf /tmp/pg_cron* \
    && apt-get purge -y build-essential curl make \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY pg_cron.conf /opt/bitnami/postgresql/conf/conf.d/pg_cron.conf

USER 1001
