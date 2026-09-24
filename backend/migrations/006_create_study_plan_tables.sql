create table if not exists public.study_plans (
    id bigserial primary key,
    user_id bigint references public.users(id) on delete cascade,
    auth_id uuid not null,
    title text not null default '학습 계획',
    created_at timestamp with time zone default now()
);

create table if not exists public.plan_blocks (
    id bigserial primary key,
    plan_id bigint not null references public.study_plans(id) on delete cascade,
    unit_key text,
    title text not null,
    start_at timestamp with time zone not null,
    end_at timestamp with time zone,
    minutes integer,
    done boolean not null default false,
    reminder_sent boolean not null default false,
    created_at timestamp with time zone default now()
);

create table if not exists public.user_notification_settings (
    auth_id uuid primary key,
    enabled boolean not null default true,
    reminder_minutes_before integer not null default 10,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);