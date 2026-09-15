import { useState } from 'react';
import { readStorage, writeStorage } from '@/lib/storage';
const key = 'metiquo:favorites';
const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((v) => typeof v === 'string');
export function useFavorites() {
  const [favorites, setFavorites] = useState(() => readStorage<string[]>(key, [], isStringArray));
  function toggle(id: string) {
    setFavorites((previous) => {
      const next = previous.includes(id)
        ? previous.filter((item) => item !== id)
        : [...previous, id];
      writeStorage(key, next);
      return next;
    });
  }
  return { favorites, toggle };
}
