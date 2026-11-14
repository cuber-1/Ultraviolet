// Favourite roofs, kept in this browser across searches (a per-viewer convenience).
export type Favorite = {
  id: string; name: string; address: string; imageryUrl: string; city: string;
  sunlitSqft: number | null; fit: number | null; startMonth: number | null; crops: string[]; savedAt: string;
};

const KEY = 'ultraviolet.favorites';

export function loadFavorites(): Favorite[] {
  try { const raw = localStorage.getItem(KEY); return raw ? JSON.parse(raw) as Favorite[] : []; } catch { return []; }
}

function store(items: Favorite[]) {
  try { localStorage.setItem(KEY, JSON.stringify(items)); } catch { /* storage unavailable: favourites last for this visit only */ }
}

export function addFavorite(item: Favorite) {
  const next = [item, ...loadFavorites().filter((existing) => existing.id !== item.id)];
  store(next); return next;
}

export function removeFavorite(id: string) {
  const next = loadFavorites().filter((existing) => existing.id !== id);
  store(next); return next;
}
