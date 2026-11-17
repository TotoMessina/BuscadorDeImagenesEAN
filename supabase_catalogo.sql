-- =============================================================================
-- Catálogo compartido del equipo para el Buscador de EAN e Imágenes
-- Ejecutar UNA vez en Supabase: panel del proyecto → SQL Editor → New query → pegar todo → Run
-- =============================================================================

create table if not exists public.productos_catalogo (
    id              bigint generated always as identity primary key,
    clave           text not null unique,      -- nombre normalizado (así se reconoce el producto en otras listas)
    nombre_original text,                      -- cómo venía escrito en la lista donde se cargó
    ean             text,
    imagen_url      text,
    match_nombre    text,                      -- nombre del producto en la tienda
    marca           text,
    categoria       text,
    contenido_neto  text,
    descripcion     text,
    link_producto   text,
    fuente_ean      text,
    fuente_imagen   text,
    score           numeric,
    confirmado      boolean not null default false,  -- true = lo eligió/revisó una persona
    usos            integer not null default 0,      -- cuántas veces se reutilizó en búsquedas
    creado          timestamptz not null default now(),
    actualizado     timestamptz not null default now()
);

create index if not exists productos_catalogo_ean_idx on public.productos_catalogo (ean);

-- Mantener "actualizado" al día en cada cambio
create or replace function public.productos_catalogo_actualizado()
returns trigger language plpgsql as $$
begin
    new.actualizado := now();
    return new;
end $$;

drop trigger if exists productos_catalogo_actualizado on public.productos_catalogo;
create trigger productos_catalogo_actualizado
    before update on public.productos_catalogo
    for each row execute function public.productos_catalogo_actualizado();

-- Sumar un uso sin tener que leer y reescribir la fila
create or replace function public.catalogo_sumar_uso(p_id bigint)
returns void language sql as $$
    update public.productos_catalogo set usos = usos + 1 where id = p_id;
$$;

-- Seguridad: con RLS activado y sin políticas, nadie puede leer ni escribir con la clave pública.
-- El buscador usa la clave secreta (solo en el servidor), que no pasa por RLS.
alter table public.productos_catalogo enable row level security;
revoke all on public.productos_catalogo from anon, authenticated;
revoke execute on function public.catalogo_sumar_uso(bigint) from anon, authenticated, public;

-- Después de esto, ejecutar también supabase_similares.sql (búsqueda de productos parecidos).
