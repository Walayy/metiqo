import { createContext } from 'react';

// Navigation establishes a new baseline; it is not a live data update.
export const ObservationScope = createContext<string | number | null>(null);
