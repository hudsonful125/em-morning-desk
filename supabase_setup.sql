-- supabase_setup.sql: run this once in Supabase's SQL Editor (see the README,
-- "Accounts with email and password"). It makes the table for drill scores and
-- locks it so each person can only see and add their own rows.

create table if not exists drill_results (
  id             bigint generated always as identity primary key,
  user_id        uuid not null default auth.uid() references auth.users on delete cascade,
  date           text not null,
  question_type  text not null,
  correct        integer not null,
  seconds        real not null,
  question       text,
  your_answer    text,
  right_answer   real
);

alter table drill_results enable row level security;

drop policy if exists "Read your own scores" on drill_results;
create policy "Read your own scores" on drill_results
  for select to authenticated using (auth.uid() = user_id);

drop policy if exists "Save your own scores" on drill_results;
create policy "Save your own scores" on drill_results
  for insert to authenticated with check (auth.uid() = user_id);

grant select, insert on drill_results to authenticated;
