import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function HeroSection() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      {/* Animated grid background */}
      <div className="absolute inset-0 grid-overlay opacity-40" />
      <div className="absolute inset-0 scanline pointer-events-none" />
      
      {/* Radial gradient overlay */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_hsl(135_100%_50%_/_0.04)_0%,_transparent_70%)]" />

      <div className="relative z-10 container mx-auto px-4 text-center">
        {/* Live badge */}
        <div className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/5 px-4 py-1.5 mb-8 animate-fade-in-up">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
          </span>
          <span className="font-mono text-xs text-primary">LIVE</span>
          <span className="text-xs text-muted-foreground">AI-Powered OSINT Intelligence</span>
        </div>

        {/* Headline */}
        <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight mb-6 animate-fade-in-up" style={{ animationDelay: "0.1s" }}>
          Intelligence. Open Source.
          <br />
          <span className="text-primary text-glow">Real-Time.</span>
        </h1>

        {/* Subheadline */}
        <p className="max-w-2xl mx-auto text-muted-foreground text-lg md:text-xl mb-10 animate-fade-in-up" style={{ animationDelay: "0.2s" }}>
          Multi-agent AI system that monitors global conflicts across GEOINT, SIGINT, SOCMINT, FININT & TECHINT — synthesized into actionable intelligence briefs.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-6 animate-fade-in-up" style={{ animationDelay: "0.3s" }}>
          <Button asChild size="lg" className="min-w-[180px]">
            <Link to="/signup">Get Access</Link>
          </Button>
          <Button asChild variant="outline" size="lg" className="min-w-[180px]">
            <Link to="/login">Log In</Link>
          </Button>
        </div>

        <p className="text-xs text-muted-foreground mb-16 animate-fade-in-up" style={{ animationDelay: "0.4s" }}>
          No credit card required · Free tier available
        </p>

        {/* Stats */}
        <div className="font-mono text-sm text-muted-foreground animate-fade-in-up" style={{ animationDelay: "0.5s" }}>
          <span className="text-primary">23</span> Conflicts Monitored ·{" "}
          <span className="text-primary">847</span> Signals Today ·{" "}
          Last Brief: <span className="text-primary">4 min ago</span>
        </div>
      </div>
    </section>
  );
}
