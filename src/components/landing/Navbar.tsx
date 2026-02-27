import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="container mx-auto flex h-16 items-center justify-between px-4">
        <Link to="/" className="font-mono font-bold text-lg text-primary text-glow tracking-wider">
          DIGITAL WAR ROOM
        </Link>
        <div className="flex items-center gap-4">
          <Link to="/login" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
            Log In
          </Link>
          <Button asChild size="sm">
            <Link to="/signup">Get Access</Link>
          </Button>
        </div>
      </div>
    </nav>
  );
}
