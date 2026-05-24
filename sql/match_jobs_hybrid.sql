-- Supabase SQL Editor에서 실행하여 match_jobs_hybrid 함수를 정상 작동하도록 복구/재생성하는 SQL 스크립트입니다.
-- 이 함수는 jobs와 job_seoul_50 테이블의 공고 데이터를 통합하여 하이브리드 추천을 지원합니다.
-- j.id 와 리턴 테이블 정의의 id 명칭이 충돌하는 모호성 에러(column reference "id" is ambiguous)를 방지하기 위해 
-- #variable_conflict use_column 지시어를 지정하고 c.id 와 c.embedding 등을 명시적으로 타겟팅합니다.

DROP FUNCTION IF EXISTS public.match_jobs_hybrid(vector, integer);

CREATE OR REPLACE FUNCTION public.match_jobs_hybrid(
  query_embedding vector(1536),
  match_count int
)
RETURNS TABLE (
  id bigint,
  title text,
  company text,
  content text,
  url text,
  location text,
  salary text,
  deadline text,
  similarity float
)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
BEGIN
  RETURN QUERY
  WITH combined_jobs AS (
    SELECT
      j.id,
      j.title,
      j.company,
      j.content,
      j.url,
      j.location,
      j.salary,
      j.deadline::text AS deadline,
      j.embedding
    FROM public.jobs j
    WHERE j.embedding IS NOT NULL
    
    UNION ALL
    
    SELECT
      s.id,
      s.title,
      s.company_or_org AS company,
      s.occupation_name AS content,
      s.source_url AS url,
      s.event_location AS location,
      s.pay_text AS salary,
      s.apply_end AS deadline,
      s.embedding
    FROM public.job_seoul_50 s
    WHERE s.embedding IS NOT NULL
  )
  SELECT
    c.id,
    c.title,
    c.company,
    c.content,
    c.url,
    c.location,
    c.salary,
    c.deadline,
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM combined_jobs c
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
