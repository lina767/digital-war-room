# Branch Protection (CI must pass)

Damit niemand in `main` mergen kann, wenn die CI fehlschlägt, solltest du Branch-Protection-Regeln in GitHub aktivieren.

## Schritte (GitHub UI)

1. **Repository** → **Settings** → **Branches**
2. Unter **Branch protection rules** auf **Add rule** (bzw. bestehende Rule für `main` bearbeiten)
3. **Branch name pattern:** `main` (oder `master`, je nach Default-Branch)
4. Aktivieren:
   - **Require a pull request before merging** (optional, aber empfohlen)
   - **Require status checks to pass before merging**
   - Bei **Status checks** die CI-Jobs auswählen, die grün sein müssen, z. B.:
     - `Backend lint (ruff)`
     - `Backend tests (pytest + coverage)`
     - `Frontend tests (vitest)`
     - `Type checks (TypeScript + mypy)`
5. **Save** / **Create**

Danach kann in den gewählten Branch nur noch gemerged werden, wenn die angehakten Status-Checks erfolgreich durchgelaufen sind.

**Hinweis:** Branch-Protection-Regeln können nur Repo-Administratoren setzen.
