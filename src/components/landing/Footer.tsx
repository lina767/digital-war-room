import { Link } from "react-router-dom";
import { useScrollReveal } from "@/hooks/use-scroll-reveal";

export function Footer() {
  const { ref, isVisible } = useScrollReveal({ threshold: 0.2 });

  return (
    <footer ref={ref} className={`border-t border-border py-12 transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"}`}>
      <div className="container mx-auto px-4">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6 mb-8">
          <div>
            <div className="font-mono font-bold text-primary text-glow tracking-wider mb-1">DIGITAL WAR ROOM</div>
            <p className="text-xs text-muted-foreground">AI-Powered OSINT Intelligence Platform</p>
          </div>
          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <a href="#features" className="hover:text-foreground transition-colors">Features</a>
            <Link to="/login" className="hover:text-foreground transition-colors">Login</Link>
            <Link to="/signup" className="hover:text-foreground transition-colors">Get Access</Link>
          </div>
        </div>
        <div className="text-center text-xs text-muted-foreground">
          © 2025 Digital War Room · For research and educational purposes only. Not affiliated with any government or intelligence agency.
        </div>
      </div>
    </footer>
  );
}
