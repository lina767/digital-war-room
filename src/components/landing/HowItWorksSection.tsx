import { Target, Cpu, FileText, ArrowRight } from "lucide-react";
import { useScrollReveal } from "@/hooks/use-scroll-reveal";

const steps = [
  { icon: Target, num: "01", title: "Select Your Conflict", description: "Choose from active conflicts or add a custom scenario." },
  { icon: Cpu, num: "02", title: "Agents Collect & Analyze", description: "Five AI agents run in parallel, pulling from 20+ open sources." },
  { icon: FileText, num: "03", title: "Receive Your Brief", description: "Structured BLUF brief with escalation score and scenarios." },
];

export function HowItWorksSection() {
  const { ref: headerRef, isVisible: headerVisible } = useScrollReveal();

  return (
    <section className="py-24 border-t border-border">
      <div className="container mx-auto px-4">
        <div
          ref={headerRef}
          className={`text-center mb-16 transition-all duration-700 ${headerVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
        >
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            From Raw Data to Intelligence Brief <span className="text-primary">in Minutes</span>
          </h2>
        </div>

        <div className="flex flex-col md:flex-row items-center justify-center gap-6 md:gap-4 max-w-4xl mx-auto">
          {steps.map((step, i) => (
            <StepItem key={step.num} step={step} index={i} isLast={i === steps.length - 1} />
          ))}
        </div>
      </div>
    </section>
  );
}

function StepItem({ step, index, isLast }: { step: typeof steps[0]; index: number; isLast: boolean }) {
  const { ref, isVisible } = useScrollReveal({ threshold: 0.2 });

  return (
    <div ref={ref} className="flex items-center gap-4">
      <div
        className={`flex flex-col items-center text-center w-56 transition-all duration-600 ${
          isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
        }`}
        style={{ transitionDelay: isVisible ? `${index * 150}ms` : "0ms" }}
      >
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-primary/30 bg-primary/5 mb-4">
          <step.icon className="h-6 w-6 text-primary" />
        </div>
        <span className="font-mono text-xs text-primary mb-1">STEP {step.num}</span>
        <h3 className="font-semibold mb-2">{step.title}</h3>
        <p className="text-sm text-muted-foreground">{step.description}</p>
      </div>
      {!isLast && (
        <ArrowRight
          className={`hidden md:block h-5 w-5 text-muted-foreground flex-shrink-0 transition-all duration-500 ${
            isVisible ? "opacity-100 translate-x-0" : "opacity-0 -translate-x-4"
          }`}
          style={{ transitionDelay: isVisible ? `${index * 150 + 100}ms` : "0ms" }}
        />
      )}
    </div>
  );
}
