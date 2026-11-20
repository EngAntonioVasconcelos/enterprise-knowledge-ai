// The organization's technical name, made from the name the person types:
// "Atl\u00e2ntico Seguros, S.A." becomes "atlantico-seguros-s-a". The
// person never has to invent one.
export function slugify(name: string): string {
  const slug = name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
    .replace(/-+$/g, "");
  return slug.length >= 2 ? slug : "org";
}
