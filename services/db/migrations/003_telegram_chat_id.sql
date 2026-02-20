-- Telegram chat ID — allows lookup when channel username is unavailable.
-- Populated by the ingester when it first sees a channel; used to match
-- messages from channels that have no username or return None.

ALTER TABLE sources
ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_sources_telegram_chat_id
ON sources(telegram_chat_id) WHERE platform = 'telegram' AND telegram_chat_id IS NOT NULL;
