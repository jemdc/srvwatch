-- Migration: Add unique constraint on (server_id, gpu_index) to prevent data duplication
-- Run this once against your TimescaleDB instance after deploying the fix

-- Create unique index if it doesn't exist
CREATE UNIQUE INDEX IF NOT EXISTS idx_server_gpu ON metrics (server_id, gpu_index);

-- Verify index creation
SELECT indexname FROM pg_indexes 
WHERE tablename = 'metrics' AND indexname LIKE '%idx_server_gpu%';
