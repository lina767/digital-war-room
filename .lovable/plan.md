
## Forgot Password einrichten

### Was wird gebaut
Eine vollständige "Passwort vergessen"-Funktion mit zwei Teilen:
1. **Forgot Password Dialog** auf der Login-Seite — User gibt E-Mail ein und erhält einen Reset-Link
2. **Reset Password Seite** (`/reset-password`) — User setzt ein neues Passwort

### Änderungen

**1. Neue Seite: `src/pages/ResetPassword.tsx`**
- Formular mit zwei Feldern: neues Passwort + Bestätigung
- Prüft beim Laden, ob ein `type=recovery` Token im URL-Hash vorhanden ist
- Ruft `supabase.auth.updateUser({ password })` auf
- Zeigt Erfolgs-/Fehlermeldung und leitet zum Login weiter
- Gleiches Design wie Login/Signup (DIGITAL WAR ROOM Branding, dunkles Card-Layout)

**2. Neue Komponente: `src/components/ForgotPasswordDialog.tsx`**
- Dialog/Modal das sich öffnet wenn "Forgot password?" geklickt wird
- E-Mail-Eingabefeld
- Ruft `supabase.auth.resetPasswordForEmail(email, { redirectTo: origin + '/reset-password' })` auf
- Zeigt Bestätigung: "Falls ein Konto existiert, wurde eine E-Mail gesendet"

**3. Login-Seite aktualisieren: `src/pages/Login.tsx`**
- Den bestehenden "Forgot password?" Button mit dem neuen Dialog verbinden

**4. Route hinzufügen: `src/App.tsx`**
- Neue Route: `<Route path="/reset-password" element={<ResetPassword />} />`
- Öffentliche Route (nicht hinter ProtectedRoute)

### Technische Details
- Verwendet die eingebaute Authentifizierung — keine Datenbankänderungen nötig
- `resetPasswordForEmail` sendet automatisch eine E-Mail mit Reset-Link
- Der Reset-Link leitet zurück zur App auf `/reset-password` mit einem Recovery-Token
- `updateUser({ password })` setzt das neue Passwort
