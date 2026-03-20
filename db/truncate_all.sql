-- Truncate all data (order: children first, then parents). RESTART IDENTITY resets serials.
TRUNCATE TABLE trades, messages, message_batches, participants, groups RESTART IDENTITY CASCADE;
