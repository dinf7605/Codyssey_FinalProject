-- 과거 OpenAI 임베딩 설계 기록. 현재 Claude 제목 추천에는 사용하지 않으며 새 배포에 적용할 필요가 없다.
create or replace function public.match_contest_titles(
  query_embedding vector(1536), match_count integer default 20,
  min_similarity double precision default 0.62
)
returns table(contest_id uuid, similarity double precision)
language sql stable security definer
set search_path = public
as $$
  select e.contest_id, 1 - (e.embedding <=> query_embedding) as similarity
  from public.contest_embeddings e
  join public.contests c on c.id = e.contest_id
  where e.index_status = 'indexed'
    and e.embedding is not null
    and c.source = 'wevity'
    and (c.deadline is null or c.deadline >= current_date)
    and 1 - (e.embedding <=> query_embedding) >= min_similarity
  order by e.embedding <=> query_embedding
  limit least(greatest(match_count, 1), 20);
$$;

revoke all on function public.match_contest_titles(vector, integer, double precision) from public, anon, authenticated;
grant execute on function public.match_contest_titles(vector, integer, double precision) to service_role;
