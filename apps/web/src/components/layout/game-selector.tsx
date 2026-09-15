import { Select } from 'radix-ui';
import { Check, ChevronDown } from 'lucide-react';
import { games } from '@/domain/games';
import { Logo } from '@/components/ui/logo';

export function GameSelector() {
  const current = games[0];
  return (
    <Select.Root value={current.id}>
      <Select.Trigger className="game-selector" aria-label="Choisir un jeu" type="button">
        <Logo src={current.image} name={current.name} code={current.shortName} />
        <span className="game-selection-label">
          <strong>{current.name}</strong>
          <span>Votre terrain de jeu</span>
        </span>
        <Select.Icon>
          <ChevronDown size={14} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          className="select-content game-options"
          position="popper"
          sideOffset={8}
          align="start"
          collisionPadding={12}
        >
          <Select.Viewport>
            {games.map((game) => (
              <Select.Item
                key={game.id}
                value={game.id}
                disabled={!game.available}
                className="select-item game-option"
                textValue={game.name}
              >
                <Logo src={game.image} name={game.name} code={game.shortName} />
                <Select.ItemText>{game.name}</Select.ItemText>
                {!game.available && <span className="coming-soon">À venir</span>}
                <Select.ItemIndicator>
                  <Check size={15} />
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
