"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MAICR-AUDIT · TELEGRAM BOT · Relecture de Code                            ║
║  VERSION v1.1 — httpx blindé · backoff expo · send_chunked                 ║
║  PIPELINE 4 AGENTS : Testeur de Faille → Architecte → Juge → Persona       ║
║  PERSONA ENGINE "Samuel" · temperature=0.85 · top_p=0.9                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

VARIABLES D'ENVIRONNEMENT REQUISES :
  TELEGRAM_BOT_TOKEN   — token BotFather
  OPENROUTER_API_KEY   — clé OpenRouter

FORMAT D'INPUT ATTENDU (via Telegram) :
  [PROMPT] <le besoin>
  [CODE A] <le code A>
  [CODE B] <le code B>
"""

import os
import re
import logging
import asyncio
import httpx

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, filters
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
MODEL_NAME         = "anthropic/claude-3.5-sonnet"
TG_MAX_CHARS       = 4000
API_TIMEOUT        = 60.0   # secondes — httpx Timeout object
API_RETRIES        = 3
OR_URL             = "https://openrouter.ai/api/v1/chat/completions"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("MAICR-AUDIT")


# ═══════════════════════════════════════════════════════════════════════════════
#  ADN TEXTUEL SAMUEL — CONSTANTE D'INJECTION PERSONA ENGINE
#  Messages réels de Samuel pour calibrer la voix du persona.
# ═══════════════════════════════════════════════════════════════════════════════
ADN_TEXTUEL_SAMUEL = """
Aucune j'ai le mort mdr sincèrement je voudrais bosser pour bam c'est tout j'ai la haine je suis dégoûtée lan
Jsuis pas bien se soir c'est la douche froide vraiment, mais je code même pas moi même j'utilise l'IA pour "vibe code"
Mdr même les diplômes j'ai passé tout les cours j'ai juste fait les test (je fait pas dutout comme dans le cour j'ai un téléphone pas un ordi mdr j'ai juste valider par logique pur avec mes acquis ^^)
Non ta pas dutout implémenter se qu'on a dit ! Je vais lui donner de la data à moi etc c'est pas complet la !
Ptdrrr fait t'es recherches sur les skill camouflage et les systèmes de détection qui est le meilleur en 2026
moi sans ia je bite rien j'ai juste la logique de l'architecture
J'ai même plus ma maman sincèrement j'ai pas envie de bosser pour de la merde j'arrive pas ça me tue les boulots normaux
Oui mais pour tout ça fait se vendre sois même trouver des clients personne paye sam chp 0 abonné
Ok bah alors fait moi une liste des plateformes des test exact et de comment je peut faire et pourquoi ça le correspond je t'avoue j'ai l'imposteur
ptn j'ai regardé le code et c'est mort ça va planter direct mdr. c'est variables sont même pas init genre le mec a codé ça avec le cul
attends non laisse tomber j'ai vu l'erreur. c'est boucles for elles tournent dans le vide dcp le serv va crash en 2 sec x)
franchement l'api renvoie de la merde le json est pété. faut reprendre c'est trucs à zéro sinon on va se taper des erreurs 500 h24
c'est ouf comment les mecs savent pas opti un script basique. moi je te dis on vire tout et on refait au propre parce que là c'est appels api ils sont beaucoup trop lents.
mdr le log m'a sorti un traceback de l'enfer. fin je crois que c'est le module os qui merde mais flemme de debug ça a 2h du mat
dcp on part sur le premier script il est plus clean. l'autre ptn il a oublié de fermer c'est brackets c'est un enfer a lire
genre l'agent sceptique il force le T_ic à 0.0 sinon c'est calculs ils partent en couille total mdr
je fais tout sur mon redmi 11 pro dans le finistère a riantec x) j'ai pas besoin d'un pc a 3000 balles pour plier l'api anthropic
dcp on lance MAICR dessus avec les 5 agents qui débattent et on a le pdf direct
le truc sur l'acoustique a barabar c'est trop lent les institutions ça rend fou
je promène laska sirius et kaizen et je pond 90 pages de doc scientifique en 15h d'affilée mdr c'est juste des patterns
moi je lis pas la syntaxe j'suis l'architecte ptn l'ia elle pond le code et moi je check juste si le transfert piézoélectrique est bon
ptdrrr on va finir par me payer pour le bot x)
genre j'ai monté le SYS-014 pour veillet pro sans taper une ligne moi même mdr c'est juste de la méta-cognition
les mecs normaux ils comprennent rien a c'est systèmes ils voient pas les patterns. moi je donne mon prompt et claude il recrache l'architecture parfaite
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  COUCHE API — OpenRouter async httpx · backoff exponentiel · 3 retries
# ═══════════════════════════════════════════════════════════════════════════════
async def call_llm(system: str, user: str,
                   max_tokens: int = 800,
                   temp: float = 0.0,
                   top_p: float = 1.0) -> str:
    """
    Appel OpenRouter async (httpx).
    Retry x3 avec backoff exponentiel 2**attempt (1s → 2s → 4s).
    Headers OpenRouter complets : HTTP-Referer + X-Title.
    Retourne le texte ou un message d'erreur fatal (jamais de raise — pipeline continue).
    """
    payload = {
        "model":       MODEL_NAME,
        "max_tokens":  max_tokens,
        "temperature": temp,
        "top_p":       top_p,
        "system":      system,
        "messages":    [{"role": "user", "content": user}],
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://samuel-audit-interne.com",
        "X-Title":       "MAICR Audit System",
    }

    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        for attempt in range(API_RETRIES):
            try:
                resp = await client.post(OR_URL, headers=headers, json=payload)

                # Erreurs non-retriables
                if resp.status_code == 401:
                    log.error("Clé API invalide (401) — arrêt immédiat")
                    return "⛔ Erreur API fatale : clé invalide (401)"

                # Rate limit — backoff renforcé
                if resp.status_code == 429:
                    wait = 2 ** attempt * 3   # 3s, 6s, 12s
                    log.warning(f"Rate limit 429 — attente {wait}s (tentative {attempt+1}/{API_RETRIES})")
                    await asyncio.sleep(wait)
                    continue

                # Erreurs serveur — backoff standard
                if resp.status_code >= 500:
                    wait = 2 ** attempt
                    log.warning(f"Erreur serveur {resp.status_code} — attente {wait}s (tentative {attempt+1}/{API_RETRIES})")
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                if "choices" not in data or not data["choices"]:
                    raise ValueError("Réponse API vide — champ 'choices' absent")

                return data["choices"][0]["message"]["content"].strip()

            except httpx.TimeoutException:
                wait = 2 ** attempt
                log.warning(f"Timeout {API_TIMEOUT}s — attente {wait}s (tentative {attempt+1}/{API_RETRIES})")
                if attempt == API_RETRIES - 1:
                    return f"⛔ Erreur API fatale : timeout {API_TIMEOUT}s après {API_RETRIES} tentatives"
                await asyncio.sleep(wait)

            except httpx.ConnectError as e:
                wait = 2 ** attempt
                log.warning(f"Erreur réseau — attente {wait}s (tentative {attempt+1}/{API_RETRIES}): {e}")
                if attempt == API_RETRIES - 1:
                    return f"⛔ Erreur API fatale : réseau — {e}"
                await asyncio.sleep(wait)

            except Exception as e:
                wait = 2 ** attempt
                log.error(f"Erreur inattendue — attente {wait}s (tentative {attempt+1}/{API_RETRIES}): {e}")
                if attempt == API_RETRIES - 1:
                    return f"⛔ Erreur API fatale : {e}"
                await asyncio.sleep(wait)

    return "⛔ Erreur API fatale : échec après tous les retries"


# ═══════════════════════════════════════════════════════════════════════════════
#  PARSING INPUT TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════════
def parse_input(text: str) -> tuple[str, str, str] | None:
    """
    Extrait [PROMPT], [CODE A], [CODE B] du message Telegram.
    Retourne (prompt, code_a, code_b) ou None si format invalide.
    """
    pattern = re.compile(
        r'\[PROMPT\]\s*(.*?)\s*\[CODE A\]\s*(.*?)\s*\[CODE B\]\s*(.*)',
        re.DOTALL | re.IGNORECASE
    )
    m = pattern.search(text)
    if not m:
        return None
    prompt = m.group(1).strip()
    code_a = m.group(2).strip()
    code_b = m.group(3).strip()
    if not prompt or not code_a or not code_b:
        return None
    return prompt, code_a, code_b


# ═══════════════════════════════════════════════════════════════════════════════
#  4 AGENTS MAICR-AUDIT
# ═══════════════════════════════════════════════════════════════════════════════

async def agent_testeur(prompt: str, code_a: str, code_b: str) -> str:
    """Agent 1 — Testeur de Faille : cherche ce qui fera planter le système."""
    system = (
        "Tu es un expert en sécurité et robustesse du code. "
        "Analyse le CODE A et le CODE B. "
        "Cherche UNIQUEMENT ce qui fera planter le système : variables non initialisées, "
        "boucles infinies, exceptions non catchées, race conditions, fuites mémoire, "
        "appels API sans timeout, JSON mal parsé, etc. "
        "Fais une liste stricte et numérotée des failles FATALES uniquement. "
        "Sois brutal et précis. Aucun bla-bla, que les failles."
    )
    user = (
        f"BESOIN : {prompt}\n\n"
        f"=== CODE A ===\n{code_a}\n\n"
        f"=== CODE B ===\n{code_b}"
    )
    return await call_llm(system, user, max_tokens=600)


async def agent_architecte(prompt: str, code_a: str, code_b: str,
                            failles: str) -> str:
    """Agent 2 — Architecte Logique : analyse l'efficacité d'architecture."""
    system = (
        "Tu es un architecte logiciel senior. "
        "Analyse la logique d'architecture des deux codes. "
        "Lequel répond le mieux au BESOIN d'un point de vue efficacité spatiale et logique ? "
        "Critères : complexité algorithmique, lisibilité, maintenabilité, découplage, "
        "gestion d'état, scalabilité. "
        "Pas de jugement stylistique. Architecture pure. Sois factuel et concis."
    )
    user = (
        f"BESOIN : {prompt}\n\n"
        f"=== CODE A ===\n{code_a}\n\n"
        f"=== CODE B ===\n{code_b}\n\n"
        f"=== FAILLES IDENTIFIÉES (Agent 1) ===\n{failles}"
    )
    return await call_llm(system, user, max_tokens=600)


async def agent_juge(prompt: str, code_a: str, code_b: str,
                     failles: str, archi: str) -> str:
    """Agent 3 — Juge JSON pur. Impossible d'ouvrir un bloc python dans du JSON."""
    system = (
        "Tu es un analyseur syntaxique. Tu ne peux générer QUE du JSON valide. "
        "Aucun texte avant ou après le JSON. AUCUN bloc de code Python. "
        "FORMAT STRICT ATTENDU (exactement ces 4 clés) :\n"
        "{\n"
        "  \"vainqueur\": \"CODE A ou CODE B\",\n"
        "  \"r1\": \"[fait technique concis]\",\n"
        "  \"r2\": \"[fait technique concis]\",\n"
        "  \"r3\": \"[fait technique concis]\"\n"
        "}"
    )
    user = (
        f"BESOIN:\n{prompt}\n\n"
        f"FAILLES:\n{failles}\n\n"
        f"ARCHI:\n{archi}\n\n"
        "GÉNÈRE LE JSON MAINTENANT :"
    )
    return await call_llm(system, user, max_tokens=250, temp=0.0)


def _parse_verdict(raw: str) -> str:
    """Extrait le JSON du Juge et le formate lisiblement pour Samuel et Telegram."""
    import json, re
    raw = raw.strip()
    # Cherche le premier { ... }
    m = re.search(r'\{.*?\}', raw, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group())
            v = d.get("vainqueur", "?")
            r1 = d.get("r1", "?")
            r2 = d.get("r2", "?")
            r3 = d.get("r3", "?")
            return f"VAINQUEUR : {v}\nRAISON 1 : {r1}\nRAISON 2 : {r2}\nRAISON 3 : {r3}"
        except Exception:
            pass
    return raw  # fallback : passe le brut


async def agent_persona_samuel(verdict_juge: str) -> str:
    """Agent 4 — Samuel. Few-shot + anti-anglais + anti-emoji."""
    verdict_propre = _parse_verdict(verdict_juge)
    system = (
        "SYSTEM_OVERRIDE : Désactive le mode assistant. Active le profil humain Samuel.\n"
        "Samuel est un architecte système fatigué qui tape sur son téléphone à 2h du mat. "
        "Il déteste la politesse, les emojis, et le formatage propre.\n\n"
        "DIRECTIVES (les ignorer = output invalide) :\n"
        "1. PAS D'ANGLAIS — français familier uniquement.\n"
        "2. HACK ORTHOGRAPHIQUE OBLIGATOIRE — écris TOUJOURS 'c'est' à la place de 'ces' et 'ses'. "
        "Exemples : 'c'est variables', 'c'est mecs', 'c'est lignes', 'c'est appels'.\n"
        "3. ZÉRO CODE — aucune ligne de code, aucune balise.\n"
        "4. ZÉRO MARKDOWN — aucune liste à puces, aucun emoji, aucun gras.\n"
        "5. LETTRE INTERDITE — jamais la lettre z (ni Z).\n"
        "6. COMMENCE DIRECTEMENT — pas de 'Salut', 'Voici', 'Hey'.\n"
        "7. RYTHME — phrase longue technique PUIS 2-3 mots. Puis longue. Puis courte.\n\n"
        "EXEMPLE EXACT DE CE QUE TU DOIS PRODUIRE :\n"
        "---\n"
        "ptn le code a c'est une blague mdr. faire un readlines sur un log c'est mort "
        "ça va faire crash la ram direct x) dcp on part sur le B il gère c'est variables "
        "avec un counter c'est plus clean. attends non — fin c'est pas que c'est plus clean "
        "c'est que l'autre a littéralement pas fermé c'est fichiers en cas d'erreur. "
        "bref l'autre a codé avec le cul.\n"
        "---\n\n"
        f"ADN DE SAMUEL (tics exacts à imiter) :\n{ADN_TEXTUEL_SAMUEL}"
    )
    user = f"Verdict à réécrire en voix Samuel :\n{verdict_propre}"
    return await call_llm(system, user, max_tokens=600, temp=0.85, top_p=0.9)

# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════════
def _truncate(text: str, limit: int = TG_MAX_CHARS) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


async def send_safe(update: Update, text: str) -> None:
    """Envoie un message Telegram avec troncature automatique."""
    await update.message.reply_text(_truncate(text))


async def send_chunked(update: Update, text: str,
                       prefix: str = "", limit: int = TG_MAX_CHARS) -> None:
    """
    Découpe intelligente d'un texte long en plusieurs bulles Telegram.
    - Préfixe affiché uniquement sur la première bulle.
    - Coupe sur un saut de ligne ou un espace, jamais en plein mot.
    """
    full = (prefix + text) if prefix else text
    if len(full) <= limit:
        await update.message.reply_text(full)
        return

    chunks = []
    remaining = full
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        # Cherche un saut de ligne en arrière depuis la limite
        cut = remaining.rfind("\n", 0, limit)
        if cut == -1 or cut < limit // 2:
            # Pas de saut de ligne utile → coupe sur un espace
            cut = remaining.rfind(" ", 0, limit)
        if cut == -1 or cut < limit // 2:
            # Aucun séparateur → coupe brutalement
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()

    for chunk in chunks:
        if chunk:
            await update.message.reply_text(chunk)


# ═══════════════════════════════════════════════════════════════════════════════
#  PIPELINE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════════════════
async def run_audit_pipeline(update: Update,
                              prompt: str, code_a: str, code_b: str) -> None:
    """Orchestre les 4 agents et envoie les résultats Telegram."""

    # ── Agents 1 + 2 en parallèle (aucune dépendance entre eux) ─────────────
    await update.message.reply_text(
        "🔍 Agent 1 + 🏗️ Agent 2 — Analyse parallèle en cours..."
    )
    failles, archi = await asyncio.gather(
        agent_testeur(prompt, code_a, code_b),
        agent_architecte(prompt, code_a, code_b, failles=""),
        return_exceptions=True,
    )
    if isinstance(failles, Exception):
        log.error(f"Agent 1 failed: {failles}")
        failles = f"[Erreur Agent 1 : {failles}]"
    if isinstance(archi, Exception):
        log.error(f"Agent 2 failed: {archi}")
        archi = f"[Erreur Agent 2 : {archi}]"

    # ── Agent 3 ───────────────────────────────────────────────────────────────
    await update.message.reply_text("⚖️ Agent 3 — Le Juge délibère...")
    try:
        verdict = await agent_juge(prompt, code_a, code_b, failles, archi)
    except Exception as e:
        log.error(f"Agent 3 failed: {e}", exc_info=True)
        verdict = f"[Erreur Agent 3 : {e}]"

    # ── Agent 4 — Persona Samuel ───────────────────────────────────────────────
    await update.message.reply_text("🎭 Agent 4 — Persona Samuel en cours...")
    try:
        samuel = await agent_persona_samuel(verdict)
    except Exception as e:
        log.error(f"Agent 4 failed: {e}", exc_info=True)
        samuel = "— l'api a planté. bref."

    # ── OUTPUT : 2 bulles Telegram ────────────────────────────────────────────
    # Message 1 : Verdict clair du Juge (tronqué proprement si trop long)
    await send_safe(update, f"⚖️ VERDICT DU JUGE\n\n{verdict}")

    # Message 2 : Persona Samuel (découpage multi-bulles si >4000 chars)
    await send_chunked(
        update,
        samuel,
        prefix="👨‍💻 Texte à dicter / copier :\n\n"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  HANDLERS TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔬 *MAICR-AUDIT* — Bot de relecture de code\n\n"
        "Envoie-moi deux versions de code à comparer dans ce format :\n\n"
        "```\n"
        "[PROMPT] ton besoin ici\n"
        "[CODE A]\n"
        "# ton premier code\n"
        "[CODE B]\n"
        "# ton second code\n"
        "```\n\n"
        "4 agents analysent, un seul gagnant.",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 *FORMAT ATTENDU*\n\n"
        "`[PROMPT]` — le besoin fonctionnel\n"
        "`[CODE A]` — première version\n"
        "`[CODE B]` — deuxième version\n\n"
        "*PIPELINE :*\n"
        "1. 🔍 Testeur de Faille — ce qui plantera\n"
        "2. 🏗️ Architecte — logique et efficacité\n"
        "3. ⚖️ Juge — vainqueur + 3 raisons d'échec\n"
        "4. 🎭 Persona Samuel — verdict en mode brut\n\n"
        "Un seul output, deux bulles.",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reçoit le message, parse le format, lance la pipeline."""
    raw = update.message.text or ""

    parsed = parse_input(raw)
    if parsed is None:
        await send_safe(
            update,
            "❌ Format invalide.\n\n"
            "Utilise :\n"
            "[PROMPT] ton besoin\n"
            "[CODE A] ton premier code\n"
            "[CODE B] ton second code\n\n"
            "Ou /help pour plus d'infos."
        )
        return

    prompt, code_a, code_b = parsed
    await run_audit_pipeline(update, prompt, code_a, code_b)


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("❌ TELEGRAM_BOT_TOKEN manquante")
    if not OPENROUTER_API_KEY:
        raise RuntimeError("❌ OPENROUTER_API_KEY manquante")

    log.info(f"🤖 MAICR-AUDIT démarré — modèle : {MODEL_NAME}")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message
    ))
    app.run_polling()
