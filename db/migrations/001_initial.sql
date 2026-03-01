-- Arbitool Chat - Initial schema
-- Groups (WhatsApp groups we listen to or import from backup)
CREATE TABLE groups (
  id SERIAL PRIMARY KEY,
  external_id VARCHAR(255) NOT NULL UNIQUE,
  name VARCHAR(500) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Participants per group
CREATE TABLE participants (
  id SERIAL PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  external_id VARCHAR(255) NOT NULL,
  display_name VARCHAR(500) NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(group_id, external_id)
);

CREATE INDEX idx_participants_group_id ON participants(group_id);

-- Messages (live from bot or imported from backup)
CREATE TABLE messages (
  id SERIAL PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  sender_id INTEGER REFERENCES participants(id) ON DELETE SET NULL,
  external_id VARCHAR(255),
  content TEXT NOT NULL DEFAULT '',
  message_type VARCHAR(50) NOT NULL DEFAULT 'text',
  media_path VARCHAR(2000),
  raw_payload JSONB,
  source VARCHAR(50) NOT NULL,
  message_date TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  content_hash VARCHAR(64)
);

CREATE INDEX idx_messages_group_date ON messages(group_id, message_date);
CREATE INDEX idx_messages_group_source_processed ON messages(group_id, source, processed_at);
CREATE UNIQUE INDEX idx_messages_external_group ON messages(external_id, group_id) WHERE external_id IS NOT NULL;
CREATE INDEX idx_messages_content_hash ON messages(group_id, content_hash) WHERE content_hash IS NOT NULL;

-- Optional: batch tracking for LLM processing (can also use only Redis payload)
CREATE TABLE message_batches (
  id SERIAL PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  status VARCHAR(50) NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_message_batches_status ON message_batches(status);

-- Trades detected by LLM (buy/sell operations)
CREATE TABLE trades (
  id SERIAL PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  type VARCHAR(20) NOT NULL,
  amount NUMERIC(20, 8),
  currency VARCHAR(20),
  price_or_ref VARCHAR(500),
  message_ids BIGINT[] NOT NULL DEFAULT '{}',
  comprobante_media_path VARCHAR(2000),
  raw_llm_response JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_group_created ON trades(group_id, created_at);

-- Trigger to update groups.updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER groups_updated_at
  BEFORE UPDATE ON groups
  FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

CREATE TRIGGER message_batches_updated_at
  BEFORE UPDATE ON message_batches
  FOR EACH ROW EXECUTE PROCEDURE set_updated_at();
