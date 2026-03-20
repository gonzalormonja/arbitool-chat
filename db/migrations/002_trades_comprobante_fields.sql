-- Datos del comprobante / cliente en trades (prompt conversacional)
-- Ejecutar: psql -h localhost -p 5433 -U arbitool -d arbitool_chat -f db/migrations/002_trades_comprobante_fields.sql

-- trade_date por si no existía (algunas instalaciones lo agregaron a mano)
ALTER TABLE trades ADD COLUMN IF NOT EXISTS trade_date TIMESTAMPTZ;

-- Campos extraídos del comprobante (ordenante, banco, etc.)
ALTER TABLE trades ADD COLUMN IF NOT EXISTS bank VARCHAR(255);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS sender_name VARCHAR(500);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS cbu VARCHAR(50);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS transaction_id VARCHAR(100);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS id_colesa VARCHAR(100);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS comprobante_extra TEXT;

CREATE INDEX IF NOT EXISTS idx_trades_bank ON trades(bank) WHERE bank IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trades_sender_name ON trades(sender_name) WHERE sender_name IS NOT NULL;
