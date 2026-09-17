"""schedule partition jobs with pg_cron

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-13 21:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FUNCTIONS_SQL = r"""
CREATE TABLE IF NOT EXISTS partition_alert_log (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    table_key TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS partition_alert_state (
    table_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    missing TEXT NOT NULL DEFAULT '',
    last_notified_status TEXT,
    last_notified_missing TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION maintain_partitions()
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    i int;
    start_d date;
    end_d date;
    pname text;
    created text[] := ARRAY[]::text[];
    existing_n int;
    required_n int;
    log_text text;
BEGIN
    RAISE NOTICE '%', to_char(clock_timestamp(), 'YYYY-MM-DD HH24:MI');
    RAISE NOTICE 'Partition job started.';

    CREATE SCHEMA IF NOT EXISTS lab03;
    CREATE TABLE IF NOT EXISTS lab03.events (
        id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        event_type VARCHAR(50) NOT NULL,
        payload TEXT,
        created_at TIMESTAMP NOT NULL
    ) PARTITION BY RANGE (created_at);

    IF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'lab03' AND c.relname = 'events' AND c.relkind = 'p'
    ) THEN
        SELECT count(*) INTO existing_n
        FROM pg_inherits inh
        JOIN pg_class child ON child.oid = inh.inhrelid
        JOIN pg_class parent ON parent.oid = inh.inhparent
        JOIN pg_namespace nsp ON nsp.oid = parent.relnamespace
        WHERE parent.relname = 'events' AND nsp.nspname = 'lab03';

        required_n := 4;
        RAISE NOTICE 'Table: lab03.events';
        RAISE NOTICE 'Existing partitions: %', existing_n;
        RAISE NOTICE 'Required partitions: %', required_n;

        FOR i IN 0..3 LOOP
            start_d := CURRENT_DATE + i;
            end_d := start_d + 1;
            pname := format('events_%s', to_char(start_d, 'YYYY_MM_DD'));
            IF NOT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'lab03' AND c.relname = pname
            ) THEN
                EXECUTE format(
                    'CREATE TABLE lab03.%I PARTITION OF lab03.events
                     FOR VALUES FROM (%L) TO (%L)',
                    pname, start_d, end_d
                );
                created := created || pname;
                RAISE NOTICE 'Creating:';
                RAISE NOTICE '%', pname;
                RAISE NOTICE 'Partition created successfully.';
            END IF;
        END LOOP;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = 'bookings' AND c.relkind = 'p'
    ) THEN
        SELECT count(*) INTO existing_n
        FROM pg_inherits inh
        JOIN pg_class child ON child.oid = inh.inhrelid
        JOIN pg_class parent ON parent.oid = inh.inhparent
        JOIN pg_namespace nsp ON nsp.oid = parent.relnamespace
        WHERE parent.relname = 'bookings' AND nsp.nspname = 'public';

        RAISE NOTICE 'Table: public.bookings';
        RAISE NOTICE 'Existing partitions: %', existing_n;
        RAISE NOTICE 'Required partitions: 4';

        FOR i IN 0..3 LOOP
            start_d := (date_trunc('month', CURRENT_DATE)
                        + (i || ' months')::interval)::date;
            end_d := (date_trunc('month', CURRENT_DATE)
                      + ((i + 1) || ' months')::interval)::date;
            pname := format('bookings_%s', to_char(start_d, 'YYYY_MM'));
            IF NOT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = pname
            ) THEN
                EXECUTE format(
                    'CREATE TABLE public.%I PARTITION OF public.bookings
                     FOR VALUES FROM (%L) TO (%L)',
                    pname, start_d, end_d
                );
                created := created || pname;
                RAISE NOTICE 'Creating:';
                RAISE NOTICE '%', pname;
                RAISE NOTICE 'Partition created successfully.';
            END IF;
        END LOOP;
    END IF;

    IF created = ARRAY[]::text[] THEN
        RAISE NOTICE 'Nothing to create.';
    END IF;
    RAISE NOTICE 'Partition job finished.';

    log_text := format(
        '%s' || E'\n' || 'Partition job started.' || E'\n' ||
        'Created: %s' || E'\n' || 'Partition job finished.',
        to_char(clock_timestamp(), 'YYYY-MM-DD HH24:MI'),
        coalesce(nullif(array_to_string(created, ', '), ''), 'nothing')
    );
    RETURN log_text;
END;
$$;

CREATE OR REPLACE FUNCTION _notify_partition_health(
    p_table text,
    p_status text,
    p_missing text,
    p_horizon int,
    p_horizon_unit text
)
RETURNS TABLE(alert_sent boolean, alert_kind text, message text)
LANGUAGE plpgsql
AS $$
DECLARE
    last_status text;
    last_missing text;
    should_send boolean := false;
    kind text;
    msg text;
    checked text := to_char(clock_timestamp(), 'YYYY-MM-DD HH24:MI:SS');
BEGIN
    SELECT s.last_notified_status, s.last_notified_missing
    INTO last_status, last_missing
    FROM partition_alert_state s
    WHERE s.table_key = p_table;

    IF p_status = 'CRITICAL' AND (
        last_status IS DISTINCT FROM 'CRITICAL'
        OR last_missing IS DISTINCT FROM p_missing
    ) THEN
        should_send := true;
        kind := 'critical';
        msg := format(
            E'🚨 Partition alert\nTable: %s\nMissing partitions:\n%s\n'
            || 'Expected horizon: %s %s\nChecked at:\n%s',
            p_table,
            replace(p_missing, ',', E'\n'),
            p_horizon,
            p_horizon_unit,
            checked
        );
    ELSIF p_status = 'OK' AND last_status = 'CRITICAL' THEN
        should_send := true;
        kind := 'recovery';
        msg := format(
            E'🟢 Partition check OK\nTable: %s\n'
            || 'All required partitions exist.\nChecked at:\n%s',
            p_table,
            checked
        );
    END IF;

    INSERT INTO partition_alert_state (
        table_key, status, missing,
        last_notified_status, last_notified_missing, updated_at
    )
    VALUES (
        p_table, p_status, p_missing,
        CASE WHEN should_send THEN p_status ELSE last_status END,
        CASE WHEN should_send THEN p_missing ELSE last_missing END,
        now()
    )
    ON CONFLICT (table_key) DO UPDATE SET
        status = EXCLUDED.status,
        missing = EXCLUDED.missing,
        last_notified_status = EXCLUDED.last_notified_status,
        last_notified_missing = EXCLUDED.last_notified_missing,
        updated_at = now();

    IF should_send THEN
        INSERT INTO partition_alert_log (kind, table_key, message)
        VALUES (kind, p_table, msg);
        RAISE NOTICE '%', msg;
    END IF;

    alert_sent := should_send;
    alert_kind := kind;
    message := msg;
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION check_partition_health()
RETURNS TABLE(
    table_key text,
    status text,
    missing text,
    alert_sent boolean,
    alert_kind text,
    message text
)
LANGUAGE plpgsql
AS $$
DECLARE
    i int;
    start_d date;
    pname text;
    required text[];
    existing text[];
    miss text[];
    st text;
    rec record;
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'lab03' AND c.relname = 'events' AND c.relkind = 'p'
    ) THEN
        required := ARRAY[]::text[];
        FOR i IN 0..3 LOOP
            required := required
                || format('events_%s', to_char(CURRENT_DATE + i, 'YYYY_MM_DD'));
        END LOOP;
        SELECT coalesce(array_agg(child.relname), ARRAY[]::text[])
        INTO existing
        FROM pg_inherits inh
        JOIN pg_class child ON child.oid = inh.inhrelid
        JOIN pg_class parent ON parent.oid = inh.inhparent
        JOIN pg_namespace nsp ON nsp.oid = parent.relnamespace
        WHERE parent.relname = 'events' AND nsp.nspname = 'lab03';

        miss := ARRAY(
            SELECT r FROM unnest(required) r
            WHERE NOT r = ANY (existing)
        );
        st := CASE WHEN miss = ARRAY[]::text[] THEN 'OK' ELSE 'CRITICAL' END;
        SELECT n.*
        INTO rec
        FROM _notify_partition_health(
            'lab03.events',
            st,
            array_to_string(miss, ','),
            3,
            'days'
        ) n;
        table_key := 'lab03.events';
        status := st;
        missing := array_to_string(miss, ',');
        alert_sent := rec.alert_sent;
        alert_kind := rec.alert_kind;
        message := rec.message;
        RETURN NEXT;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = 'bookings' AND c.relkind = 'p'
    ) THEN
        required := ARRAY[]::text[];
        FOR i IN 0..3 LOOP
            start_d := (date_trunc('month', CURRENT_DATE)
                        + (i || ' months')::interval)::date;
            required := required
                || format('bookings_%s', to_char(start_d, 'YYYY_MM'));
        END LOOP;
        SELECT coalesce(array_agg(child.relname), ARRAY[]::text[])
        INTO existing
        FROM pg_inherits inh
        JOIN pg_class child ON child.oid = inh.inhrelid
        JOIN pg_class parent ON parent.oid = inh.inhparent
        JOIN pg_namespace nsp ON nsp.oid = parent.relnamespace
        WHERE parent.relname = 'bookings' AND nsp.nspname = 'public';

        miss := ARRAY(
            SELECT r FROM unnest(required) r
            WHERE NOT r = ANY (existing)
        );
        st := CASE WHEN miss = ARRAY[]::text[] THEN 'OK' ELSE 'CRITICAL' END;
        SELECT n.*
        INTO rec
        FROM _notify_partition_health(
            'public.bookings',
            st,
            array_to_string(miss, ','),
            3,
            'months'
        ) n;
        table_key := 'public.bookings';
        status := st;
        missing := array_to_string(miss, ',');
        alert_sent := rec.alert_sent;
        alert_kind := rec.alert_kind;
        message := rec.message;
        RETURN NEXT;
    END IF;
END;
$$;
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text('CREATE EXTENSION IF NOT EXISTS pg_cron'))
    conn.execute(text(FUNCTIONS_SQL))
    conn.execute(text("""
        DO $jobs$
        DECLARE
            jid bigint;
        BEGIN
            FOR jid IN
                SELECT jobid FROM cron.job
                WHERE jobname IN ('create-partitions', 'partition-health')
            LOOP
                PERFORM cron.unschedule(jid);
            END LOOP;
            PERFORM cron.schedule(
                'create-partitions',
                '0 1 * * *',
                'SELECT maintain_partitions()'
            );
            PERFORM cron.schedule(
                'partition-health',
                '5 1 * * *',
                'SELECT check_partition_health()'
            );
        END;
        $jobs$;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DO $jobs$
        DECLARE
            jid bigint;
        BEGIN
            FOR jid IN
                SELECT jobid FROM cron.job
                WHERE jobname IN ('create-partitions', 'partition-health')
            LOOP
                PERFORM cron.unschedule(jid);
            END LOOP;
        END;
        $jobs$;
    """))
    conn.execute(text('DROP FUNCTION IF EXISTS check_partition_health()'))
    conn.execute(text(
        'DROP FUNCTION IF EXISTS _notify_partition_health(text, text, text, int, text)'
    ))
    conn.execute(text('DROP FUNCTION IF EXISTS maintain_partitions()'))
    conn.execute(text('DROP TABLE IF EXISTS partition_alert_log'))
