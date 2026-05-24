-- Supabase SQL Editor에서 실행하여 match_jobs_hybrid 함수를 정상 작동하도록 복구/재생성하는 SQL 스크립트입니다.
-- 이 함수는 j.id 와 리턴 테이블 정의의 id 명칭이 충돌하는 모호성 에러(column reference "id" is ambiguous)를 방지하기 위해 
-- #variable_conflict use_column 지시어를 지정하고 j.id 와 j.embedding 등을 명시적으로 타겟팅합니다.

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
  SELECT
    j.id,
    j.title,
    j.company,
    j.content,
    j.url,
    j.location,
    j.salary,
    j.deadline,
    1 - (j.embedding <=> query_embedding) AS similarity
  FROM public.jobs j
  WHERE j.embedding IS NOT NULL
  ORDER BY j.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
