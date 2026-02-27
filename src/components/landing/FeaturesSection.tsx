import { Satellite, Radio, MessageSquare, DollarSign, Shield } from "lucide-react";

const features = [
  {
    icon: Satellite,
    title: "GEOINT",
    description: "Satellite imagery analysis, thermal anomalies, base change detection via NASA FIRMS & Sentinel Hub.",
  },
  {
    icon: Radio,
    title: "SIGINT",
    description: "Military aircraft tracking, warship movements, surveillance drones via ADSB-Exchange & MarineTraffic.",
  },
  {
    icon: MessageSquare,
    title: "SOCMINT",
    description: "Telegram channels, social media signals, early warning from eyewitness reports.",
  },
  {
    icon: DollarSign,
    title: "FININT",
    description: "Oil price spikes, prediction market odds, crypto movements by sanctioned actors.",
  },
  {
    icon: Shield,
    title: "TECHINT",
    description: "Exposed infrastructure, deleted content recovery, DNS & domain registration anomalies via Shodan.",
  },
];

export function FeaturesSection() {
  return (
    <section className="py-24 border-t border-border">
      <div className="container mx-auto px-4">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Five Intelligence Disciplines. <span className="text-primary">One Platform.</span>
          </h2>
          <p className="text-muted-foreground max-w-xl mx-auto">
            Specialized AI agents working in parallel across every open-source intelligence category.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-5xl mx-auto">
          {features.map((f, i) => (
            <div
              key={f.title}
              className={`group rounded-lg border border-border bg-card p-6 hover:border-primary/40 hover:border-glow transition-all duration-300 ${
                i === 4 ? "md:col-span-2 lg:col-span-1 lg:col-start-2" : ""
              }`}
            >
              <div className="flex items-center gap-3 mb-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <f.icon className="h-5 w-5" />
                </div>
                <h3 className="font-mono font-semibold text-primary text-sm tracking-wider">{f.title}</h3>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">{f.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
