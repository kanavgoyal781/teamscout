import { Check } from "lucide-react";

export type Step = {
  id: string;
  label: string;
};

type StepperProps = {
  steps: Step[];
  /** 0-based current step index */
  current: number;
};

export default function Stepper({ steps, current }: StepperProps) {
  return (
    <ol className="stepper" aria-label="Wizard progress">
      {steps.map((step, index) => {
        const done = index < current;
        const active = index === current;
        const cls = done ? "stepper-item done" : active ? "stepper-item active" : "stepper-item";
        return (
          <li key={step.id} className={cls} aria-current={active ? "step" : undefined}>
            {index > 0 ? <span className="stepper-connector" aria-hidden /> : null}
            <span className="stepper-dot" aria-hidden>
              {done ? <Check size={14} strokeWidth={2.5} /> : index + 1}
            </span>
            <span>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
