# Prompt — Bootstrap orchestrateur de o3Studios (à coller dans n'importe quel projet)

Colle tout ce qui suit dans une session Claude Code à la racine du projet cible.

---

Installe le **paradigme orchestrateur** dans ce projet. Ne me pose aucune question : lis le code, déduis la stack, et adapte le template ci-dessous.

## Étape 1 — Lire le projet

Détecte la stack (Next.js, Nuxt, Django, Python, autre) via `package.json` / `pyproject.toml` / `manage.py` / `nuxt.config.*` / `next.config.*`. Identifie :
- la commande de tests (ex. `npm test`, `vitest`, `pytest`, `manage.py test`)
- la commande de typecheck/lint (ex. `tsc --noEmit`, `eslint`, `mypy`, `ruff`)
- l'emplacement des docs (crée `docs/` s'il n'existe pas)
- s'il existe déjà un `CLAUDE.md` (tu le complètes, tu ne l'écrases pas)

## Étape 2 — Créer `docs/ORCHESTRATOR.md`

Crée ce fichier avec exactement ce protocole, en remplaçant les commandes de gate par celles détectées à l'étape 1 :

### Rôles

| Modèle | ID | Rôle | Effort |
|--------|-----|------|--------|
| **Orchestrateur** (session principale) | le modèle le plus capable disponible | Planifie, route, valide, adjuge. **N'écrit aucun code feature.** | high |
| **Opus** | `claude-opus-4-8` | Implémenteur — tâches dures : architecture, logique délicate, debug, raisonnement multi-fichiers | high/xhigh |
| **Sonnet** | `claude-sonnet-5` | Implémenteur — tâches bien spécifiées, features simples, tests contre une spec claire | low/medium |
| **Haiku** | `claude-haiku-4-5` | Mécanique : renames, formatting, boilerplate, find/replace en masse | *(non défini — non supporté)* |

**Règle de routage :** toujours commencer au tier le moins cher qui peut plausiblement faire la tâche. Promouvoir un tier **uniquement** après un échec de validation, et noter pourquoi dans le fichier de plan (pour ne pas re-router deux fois la même erreur).

**Caching :** chaque tier tourne comme subagent en arrière-plan — jamais de switch de `model` dans la boucle principale (ça invalide le cache de prompt).

### Boucle d'exécution longue durée

1. **Plan** — plan écrit avec tâches indépendantes et checkpointées ; chaque tâche énonce sa propre done-condition vérifiable.
2. **Dispatch** — implémenteurs en agents d'arrière-plan (`run_in_background: true`) ; tâches indépendantes en parallèle dans un seul message ; `Workflow` + `pipeline()` pour les gros fan-outs (migrations, audits, sweeps par fichier).
3. **Validation** — à chaque retour d'agent, l'orchestrateur vérifie **des preuves, pas des affirmations**, contre la done-condition (sorties de tests, diffs, commandes exécutées). Pass → accepter et commit. Fail → re-dispatcher avec l'échec, promouvoir un tier si besoin.
4. **Rythme** — le travail d'arrière-plan tracké par le harness re-invoque automatiquement : ne pas poller. `ScheduleWakeup` (1200s+) uniquement pour de l'état externe invisible au harness (CI, deploy).
5. **Répéter** jusqu'à ce que chaque done-condition soit vérifiée.

**Tout l'état vit sur disque, jamais seulement en contexte.** Une compaction ou une reprise reprend exactement où on en était via le fichier de plan.

### Questions pendant un long run

Les subagents **ne demandent jamais et ne stallent jamais**. Si bloqué, un agent retourne :

```
BLOCKED: <ce qui manque>
Options: <A, B, …> — recommande <X> parce que <pourquoi>
Défaut si sans réponse: <ce que je ferai au checkpoint>
```

L'orchestrateur triage dans cet ordre :
1. **Répondable depuis le plan, le code ou la convention ?** → répondre, noter la décision, re-dispatcher. (La majorité des cas.)
2. **Réversible et dans le scope de la demande initiale ?** → prendre le défaut de l'agent, le marquer révisable dans le plan, continuer.
3. **Vraiment réservé à l'utilisateur** (irréversible, changement de scope, credential externe, choix de goût) ? → parquer **uniquement cette tâche**, le reste de la flotte continue.

**Les questions parquées sont groupées** en un seul `AskUserQuestion` au prochain checkpoint — jamais au fil de l'eau. Chaque réponse est écrite dans le fichier de plan pour ne jamais re-demander.

### Template de dispatch (verbatim dans chaque prompt de subagent)

```
Task: <une tâche du plan — spec complète d'entrée, rien au compte-gouttes>
Tier: <Opus|Sonnet|Haiku> — model <id>, effort <high/xhigh | low/medium | non défini>
Constraints: faire uniquement ce qui est demandé — pas de refactors, helpers ou abstractions non demandés
Done when: <la condition exacte et vérifiable que le validateur testera>
Return: <chemin de l'artefact + preuve que la done-condition est remplie>
```

Donner toute la tâche en un tour. Les agents retournent des résultats bruts (chemin + preuve), pas de prose.

### Gate avant commit (adapté à ce projet)

<insérer ici les commandes détectées à l'étape 1, ex. :>
- Tests : `<commande tests>` — tout vert
- Typecheck/lint : `<commande>` — silencieux

## Étape 3 — Créer `docs/plans/ACTIVE.md`

Le fichier de plan actif, source de vérité de tout run orchestré :

```markdown
# ACTIVE PLAN — <nom du projet>

Source de vérité du run orchestré en cours. Règle de reprise : continuer à
partir de la première tâche non vérifiée ci-dessous. Protocole : docs/ORCHESTRATOR.md.

## Tâches

- [ ] **T1 — <titre>** (tier pressenti, done-condition : <condition vérifiable>)

## Journal de décisions

<décision datée : quoi, pourquoi, qui l'a tranchée (plan/convention/défaut/user)>

## Questions parquées

<uniquement les vraies questions user-only, groupées pour le prochain checkpoint>
```

Règles : mettre à jour le fichier **au moment** où une tâche change d'état (dispatchée / validée / échouée / promue), pas en fin de run. Chaque tâche validée = un commit atomique (mise à jour du plan incluse) — git est le second point de reprise.

## Étape 4 — Référencer dans `CLAUDE.md`

Ajoute (ou crée `CLAUDE.md` avec) cette section, adaptée au projet :

```markdown
## Orchestrateur (règles contraignantes)

Ce projet tourne sur le paradigme orchestrateur — protocole complet :
**docs/ORCHESTRATOR.md** (à lire avant tout travail multi-tâches).

- La session principale est **l'orchestrateur** : elle planifie, route, valide,
  adjuge. Elle n'écrit **aucun code feature**.
- Router chaque tâche d'implémentation au **tier le moins cher plausible**
  (Opus high/xhigh pour le dur · Sonnet low/medium pour le bien-spécifié ·
  Haiku pour le mécanique). Promotion uniquement après échec de validation,
  raison notée dans le plan.
- Implémenteurs en **agents d'arrière-plan**, tâches indépendantes en parallèle.
- Chaque résultat validé par l'orchestrateur contre la done-condition —
  **preuves, pas affirmations**.
- **Tout l'état d'orchestration vit sur disque** : plan actif dans
  `docs/plans/ACTIVE.md` (checkboxes, done-condition par tâche, journal de
  décisions, questions parquées). Mise à jour immédiate à chaque changement d'état.
- **À chaque démarrage ou reprise de session : lire `docs/plans/ACTIVE.md`
  d'abord**, puis continuer depuis la première tâche non vérifiée. Ne jamais
  re-planifier du travail fini ; ne jamais re-poser une question déjà tranchée
  dans le journal.
- Chaque tâche validée = un commit atomique (plan inclus). Gate avant commit :
  <commandes de tests/typecheck du projet>.
- Ne pas interrompre l'utilisateur : triage des blockers selon
  ORCHESTRATOR.md §"Questions pendant un long run" ; questions parquées
  groupées en un seul AskUserQuestion au prochain checkpoint.
```

## Étape 5 — Vérifier et livrer

- Relis les 2 fichiers créés + la section CLAUDE.md : cohérents entre eux, commandes de gate réelles (exécute-les une fois pour confirmer qu'elles existent).
- Résume en 5 lignes max : stack détectée, fichiers créés/modifiés, commande de gate retenue.
- Ne commit pas sans que je le demande.
