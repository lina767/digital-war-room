-- Add one-time reminder tracking for pending newsletter confirmations.
ALTER TABLE newsletter_subscribers
    ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMPTZ;
