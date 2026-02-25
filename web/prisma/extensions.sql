-- Enable pg_trgm for fast ILIKE / full-text similarity on segment text
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- GIN trigram index on SpeakingSegment.text — makes ILIKE '%keyword%' ~100x faster
CREATE INDEX IF NOT EXISTS idx_speaking_segment_text_trgm
  ON "SpeakingSegment" USING gin (text gin_trgm_ops);
