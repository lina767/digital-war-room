-- Allow users to create their own profile row if missing (e.g. signed up before trigger existed).
-- Run once in Supabase SQL Editor if profiles/settings are not created for existing users.

CREATE POLICY "Users can insert own profile"
  ON public.profiles FOR INSERT
  WITH CHECK (auth.uid() = id);
