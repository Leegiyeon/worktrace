CREATE TABLE IF NOT EXISTS report_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    request_id UUID NOT NULL,
    report_type TEXT NOT NULL CHECK (report_type IN ('daily', 'weekly', 'monthly')),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    as_of TEXT NOT NULL CHECK (length(btrim(as_of)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    fingerprint TEXT NOT NULL CHECK (fingerprint ~ '^[a-f0-9]{64}$'),
    schema_version TEXT NOT NULL DEFAULT '1' CHECK (schema_version = '1'),
    report_payload JSONB NOT NULL CHECK (
        jsonb_typeof(report_payload) = 'object'
        AND report_payload ? 'report_type'
        AND report_payload ? 'start_date'
        AND report_payload ? 'end_date'
        AND report_payload ? 'markdown'
        AND report_payload ? 'activity'
        AND jsonb_typeof(report_payload->'activity') = 'object'
    ),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
    CHECK (end_date >= start_date),
    CHECK ((report_payload->>'report_type') = report_type),
    CHECK ((report_payload->>'start_date')::date = start_date),
    CHECK ((report_payload->>'end_date')::date = end_date),
    CHECK ((report_payload->'activity'->>'as_of') = as_of),
    CHECK ((report_payload->'activity'->>'fingerprint') = fingerprint),
    CHECK ((report_payload->'activity'->>'schema_version') = schema_version),
    UNIQUE (owner_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_report_snapshots_owner_created_id
    ON report_snapshots (owner_id, created_at DESC, id DESC);

CREATE OR REPLACE FUNCTION worktrace_guard_report_snapshot_immutable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'report snapshots are immutable; delete and recreate with a new request_id';
END;
$$;

DROP TRIGGER IF EXISTS trg_report_snapshots_immutable_update ON report_snapshots;
CREATE TRIGGER trg_report_snapshots_immutable_update
BEFORE UPDATE ON report_snapshots
FOR EACH ROW
EXECUTE FUNCTION worktrace_guard_report_snapshot_immutable();
