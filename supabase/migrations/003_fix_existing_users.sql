-- Einmal ausführen wenn Nutzer schon VOR der Migration existierten (z.B. Account über localhost).
-- 1) Erlaubt dem Client, fehlende Profile anzulegen (INSERT Policy)
-- 2) Legt für alle bestehenden auth.users Zeilen in profiles + user_settings an

-- Policy: Nutzer dürfen eigene Profile-Zeile anlegen (für Upsert vom Frontend)
DROP POLICY IF EXISTS "Users can insert own profile" ON public.profiles;
CREATE POLICY "Users can insert own profile"
  ON public.profiles FOR INSERT
  WITH CHECK (auth.uid() = id);

-- Bestehende Nutzer: Profile + Settings anlegen (idempotent)
INSERT INTO public.profiles (id, display_name)
SELECT id, COALESCE(raw_user_meta_data->>'full_name', email)
FROM auth.users
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.user_settings (user_id)
SELECT id
FROM auth.users
ON CONFLICT (user_id) DO NOTHING;
