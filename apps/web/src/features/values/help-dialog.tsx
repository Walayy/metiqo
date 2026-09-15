import { ArrowUpRight, FlaskConical, ScanLine } from 'lucide-react';
import { Modal } from '@/components/ui/modal';
export function HelpDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      title="Voir au-delà de la cote."
      description="La value, simplement."
      className="help-dialog"
    >
      <div className="help-content">
        <span className="help-hero-icon">
          <ScanLine size={30} />
        </span>
        <h3>
          Quand la cote offre plus
          <br />
          que la probabilité estimée.
        </h3>
        <p>
          Une value apparaît lorsque la cote proposée dépasse la cote juste calculée à partir de
          votre estimation.
        </p>
        <div className="help-example">
          <div>
            <span>Probabilité estimée</span>
            <strong>60 %</strong>
          </div>
          <span>×</span>
          <div>
            <span>Cote proposée</span>
            <strong>1,80</strong>
          </div>
          <ArrowUpRight size={20} />
          <div>
            <span>Value</span>
            <strong className="text-accent">+8,0 %</strong>
          </div>
        </div>
        <code>(0,60 × 1,80 − 1) × 100 = +8,0 %</code>
        <p>
          Ce pourcentage exprime une espérance théorique basée sur une estimation. Il ne représente
          ni une certitude ni la probabilité de gagner.
        </p>
        <div className="formula-note">
          <FlaskConical size={19} />
          <div>
            <strong>Vous explorez une démonstration</strong>
            <p>
              Les ligues et équipes sont sourcées. Les affiches, horaires, cotes, historiques et
              probabilités sont fictifs. Les bookmakers sont cités à titre illustratif, sans
              affiliation. Aucun pari n’est possible.
            </p>
          </div>
        </div>
      </div>
    </Modal>
  );
}
