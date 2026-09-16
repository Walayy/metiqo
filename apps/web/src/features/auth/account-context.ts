import { createContext } from 'react';
export const AccountContext = createContext<{
  open: boolean;
  setOpen: (open: boolean) => void;
} | null>(null);
