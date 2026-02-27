

## Google OAuth reparieren

### Problem
Der Google-Login schlägt fehl mit "provider is not enabled", weil:
1. Google OAuth nicht uber Lovable Cloud konfiguriert ist
2. Der Code `supabase.auth.signInWithOAuth()` verwendet statt der Lovable Cloud Methode `lovable.auth.signInWithOAuth()`

### Loesung

**Schritt 1: Google OAuth aktivieren**
- Das "Configure Social Login" Tool verwenden, um Google als OAuth-Provider zu aktivieren
- Dies generiert automatisch die noetige Integration unter `src/integrations/lovable/`

**Schritt 2: Login-Seite aktualisieren**
- In `src/pages/Login.tsx`: Import von `lovable` hinzufuegen und `handleGoogleLogin` aendern zu:
  ```typescript
  import { lovable } from "@/integrations/lovable/index";
  
  const handleGoogleLogin = async () => {
    const { error } = await lovable.auth.signInWithOAuth("google", {
      redirect_uri: window.location.origin,
    });
    if (error) toast.error(error.message);
  };
  ```

**Schritt 3: Signup-Seite aktualisieren**
- In `src/pages/Signup.tsx`: Gleiche Aenderung fuer `handleGoogleSignup`
  ```typescript
  import { lovable } from "@/integrations/lovable/index";
  
  const handleGoogleSignup = async () => {
    const { error } = await lovable.auth.signInWithOAuth("google", {
      redirect_uri: window.location.origin,
    });
    if (error) toast.error(error.message);
  };
  ```

### Technische Details
- Lovable Cloud stellt automatisch verwaltete Google OAuth-Credentials bereit -- kein eigenes Google Cloud-Projekt noetig
- Die `lovable.auth.signInWithOAuth()` Funktion umgeht die direkte Supabase-Auth und nutzt stattdessen den Lovable Cloud OAuth-Flow
- Nach erfolgreichem Login wird der User automatisch zur App weitergeleitet

