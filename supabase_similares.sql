-- =============================================================================
-- Búsqueda de productos parecidos en el catálogo del equipo (pg_trgm)
-- Ejecutar UNA vez en Supabase (SQL Editor → New query → pegar todo → Run),
-- después de supabase_catalogo.sql. Se puede volver a ejecutar sin problema.
-- =============================================================================

create extension if not exists pg_trgm with schema extensions;

-- Índice para que la búsqueda por similitud sea rápida aunque el catálogo crezca
create index if not exists productos_catalogo_clave_trgm_idx
    on public.productos_catalogo using gin (clave extensions.gin_trgm_ops);

-- Devuelve los productos del catálogo con nombre parecido a p_clave, del más al menos parecido.
-- similitud va de 0 a 1 (1 = idéntico).
create or replace function public.catalogo_similares(p_clave text, p_limite int default 5, p_umbral real default 0.4)
returns table (
    id bigint, clave text, nombre_original text, ean text, imagen_url text, match_nombre text, marca text,
    categoria text, contenido_neto text, descripcion text, link_producto text, fuente_ean text,
    fuente_imagen text, score numeric, confirmado boolean, usos integer, similitud real
)
language sql stable
set search_path = public, extensions
as $$
    select c.id, c.clave, c.nombre_original, c.ean, c.imagen_url, c.match_nombre, c.marca,
           c.categoria, c.contenido_neto, c.descripcion, c.link_producto, c.fuente_ean,
           c.fuente_imagen, c.score, c.confirmado, c.usos,
           similarity(c.clave, p_clave) as similitud
    from public.productos_catalogo c
    where c.clave % p_clave
      and similarity(c.clave, p_clave) >= p_umbral
      and c.clave <> p_clave
    order by similitud desc, c.confirmado desc, c.usos desc
    limit least(greatest(p_limite, 1), 20);
$$;

-- Solo la clave secreta (servidor) puede usarla
revoke execute on function public.catalogo_similares(text, int, real) from anon, authenticated, public;
