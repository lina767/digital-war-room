-- User accounts: profiles (C), user_settings (A), saved_analyses (B)
-- Run in Supabase Dashboard → SQL Editor, or: supabase db push

-- Enum for user role
CREATE TYPE public.user_role AS ENUM ('user', 'admin');

-- Profiles: one per auth.users (account metadata)
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  display_name TEXT,
  role user_role NOT NULL DEFAULT 'user',
  organization TEXT
);

-- User settings: default conflict, favorites, UI state (A)
CREATE TABLE public.user_settings (
  user_id UUID PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  default_conflict TEXT NOT NULL DEFAULT 'Iran',
  favorite_conflicts JSONB NOT NULL DEFAULT '[]'::jsonb,
  ui_state JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Saved analyses (B)
CREATE TABLE public.saved_analyses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  conflict TEXT NOT NULL,
  label TEXT,
  note TEXT,
  payload JSONB NOT NULL
);

CREATE INDEX saved_analyses_user_created ON public.saved_analyses(user_id, created_at DESC);

-- Trigger: create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, display_name)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email));
  INSERT INTO public.user_settings (user_id)
  VALUES (NEW.id);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- RLS
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.saved_analyses ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own profile"
  ON public.profiles FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
  ON public.profiles FOR UPDATE
  USING (auth.uid() = id);

CREATE POLICY "Users can read own settings"
  ON public.user_settings FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can update own settings"
  ON public.user_settings FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own settings"
  ON public.user_settings FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can read own saved_analyses"
  ON public.saved_analyses FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own saved_analyses"
  ON public.saved_analyses FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own saved_analyses"
  ON public.saved_analyses FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own saved_analyses"
  ON public.saved_analyses FOR DELETE
  USING (auth.uid() = user_id);

-- If you already have users, run once to create profiles/settings:
-- INSERT INTO public.profiles (id, display_name) SELECT id, COALESCE(raw_user_meta_data->>'full_name', email) FROM auth.users ON CONFLICT (id) DO NOTHING;
-- INSERT INTO public.user_settings (user_id) SELECT id FROM auth.users ON CONFLICT (user_id) DO NOTHING;
