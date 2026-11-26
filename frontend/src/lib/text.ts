// Accents and case do not matter when searching: "ferias" finds "Ferias" written with an accent.
export function plain(text: string): string {
  return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
}
