"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MAICR-AUDIT · TELEGRAM BOT · Relecture de Code                            ║
║  VERSION v1.3 — fixes: system prompt, prefill, retry client, parse verdict  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import json
import logging
import asyncio
import httpx
import orjson

from telegram import Update
from telegram.error import RetryAfter, TimedOut, NetworkError
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
API_TIMEOUT        = 60.0
API_RETRIES        = 3
OR_URL             = "https://openrouter.ai/api/v1/chat/completions"

# Sémaphore Telegram (max 3 requêtes simultanées)
TG_SEMAPHORE = asyncio.Semaphore(3)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("MAICR-AUDIT")


# ═══════════════════════════════════════════════════════════════════════════════
#  ADN TEXTUEL SAMUEL — CONSTANTE INTACTE (NE PAS MODIFIER)
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
#  COUCHE API — OpenRouter · orjson · context manager strict
# ═══════════════════════════════════════════════════════════════════════════════
async def call_llm(system: str, user: str,
                   max_tokens: int = 800,
                   temp: float = 0.0,
                   top_p: float = 1.0,
                   custom_messages: list | None = None) -> str:
    """
    Appel OpenRouter async avec httpx context manager (fermeture propre TCP)
    et parsing orjson ultra-rapide. Retry x3 avec backoff exponentiel.

    FIX v1.3 :
    - system prompt injecté dans messages[0] (OpenAI-compat, pas clé top-level)
    - httpx.AsyncClient ouvert UNE FOIS, au-dessus de la boucle retry
    - custom_messages : system injecté en tête si absent
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://samuel-audit-interne.com",
        "X-Title":       "MAICR Audit System",
    }

    # ── Construction des messages ──────────────────────────────────────────
    if custom_messages:
        # Injecte le system en tête si le premier message n'est pas déjà system
        if custom_messages[0].get("role") != "system":
            messages = [{"role": "system", "content": system}] + custom_messages
        else:
            messages = custom_messages
    else:
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]

    payload = {
        "model":       MODEL_NAME,
        "max_tokens":  max_tokens,
        "temperature": temp,
        "top_p":       top_p,
        "messages":    messages,
        # FIX : plus de clé "system" top-level — OpenRouter l'ignore ou plante
    }

    # ── Client ouvert UNE FOIS pour tous les retries ───────────────────────
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        for attempt in range(API_RETRIES):
            try:
                resp = await client.post(OR_URL, headers=headers, json=payload)

                if resp.status_code == 401:
                    log.error("Clé API invalide (401)")
                    return "⛔ Erreur API fatale : clé invalide (401)"

                if resp.status_code == 429:
                    wait = 2 ** attempt * 3
                    log.warning(f"Rate limit 429 — attente {wait}s")
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code >= 500:
                    wait = 2 ** attempt
                    log.warning(f"Erreur serveur {resp.status_code}")
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()

                data = orjson.loads(resp.content)

                if "choices" not in data or not data["choices"]:
                    raise ValueError("Réponse API vide")
                return data["choices"][0]["message"]["content"].strip()

            except httpx.TimeoutException:
                wait = 2 ** attempt
                if attempt == API_RETRIES - 1:
                    return f"⛔ Timeout après {API_RETRIES} tentatives"
                await asyncio.sleep(wait)

            except httpx.ConnectError as e:
                wait = 2 ** attempt
                if attempt == API_RETRIES - 1:
                    return f"⛔ Erreur réseau : {e}"
                await asyncio.sleep(wait)

            except Exception as e:
                wait = 2 ** attempt
                if attempt == API_RETRIES - 1:
                    return f"⛔ Erreur fatale : {e}"
                await asyncio.sleep(wait)

    return "⛔ Échec après tous les retries"


# ═══════════════════════════════════════════════════════════════════════════════
#  PARSING INPUT
# ═══════════════════════════════════════════════════════════════════════════════
def parse_input(text: str) -> tuple[str, str, str] | None:
    """Extrait [PROMPT], [CODE A], [CODE B] du message Telegram."""
    pattern = re.compile(
        r'\[PROMPT\]\s*(.*?)\s*\[CODE A\]\s*(.*?)\s*\[CODE B\]\s*(.*)',
        re.DOTALL | re.IGNORECASE
    )
    m = pattern.search(text)
    if not m:
        return None
    prompt, code_a, code_b = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
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
    user = f"BESOIN : {prompt}\n\n=== CODE A ===\n{code_a}\n\n=== CODE B ===\n{code_b}"
    return await call_llm(system, user, max_tokens=600)


async def agent_architecte(prompt: str, code_a: str, code_b: str, failles: str) -> str:
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
        f"BESOIN : {prompt}\n\n=== CODE A ===\n{code_a}\n\n=== CODE B ===\n{code_b}\n\n"
        f"=== FAILLES IDENTIFIÉES (Agent 1) ===\n{failles}"
    )
    return await call_llm(system, user, max_tokens=600)


async def agent_juge(prompt: str, code_a: str, code_b: str,
                     failles: str, archi: str) -> str:
    """Agent 3 — Data Starvation : ne voit jamais le code source."""
    system = (
        "Tu es un arbitre technique. "
        "Lis les deux rapports et génère STRICTEMENT ces 4 lignes, rien de plus :\n"
        "VAINQUEUR : [A ou B]\n"
        "R1 : [argument technique concis]\n"
        "R2 : [argument technique concis]\n"
        "R3 : [argument technique concis]\n\n"
        "Aucun texte avant ou après ces 4 lignes."
    )
    # DATA STARVATION : code_a et code_b exclus délibérément
    user = (
        f"Rapport Failles (Agent 1) :\n{failles}\n\n"
        f"Rapport Architecture (Agent 2) :\n{archi}\n\n"
        "Sors exactement les 4 lignes demandées, rien d'autre :"
    )
    return await call_llm(system, user, max_tokens=150, temp=0.0)


def _parse_verdict(raw: str) -> str:
    """
    Extrait le verdict du Juge.
    FIX v1.3 : l'Agent 3 sort du texte brut (pas du JSON),
    on parse les 4 lignes directement sans tenter json.loads.
    """
    raw = raw.strip()

    # Tentative JSON au cas où le modèle dérape quand même
    m = re.search(r'\{.*?\}', raw, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group())
            return (
                f"VAINQUEUR : {d.get('vainqueur', '?')}\n"
                f"R1 : {d.get('r1', '?')}\n"
                f"R2 : {d.get('r2', '?')}\n"
                f"R3 : {d.get('r3', '?')}"
            )
        except Exception:
            pass

    # Parsing texte brut — format nominal attendu
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    vainqueur = r1 = r2 = r3 = "?"
    for line in lines:
        lu = line.upper()
        if lu.startswith("VAINQUEUR"):
            vainqueur = line.split(":", 1)[-1].strip()
        elif lu.startswith("R1"):
            r1 = line.split(":", 1)[-1].strip()
        elif lu.startswith("R2"):
            r2 = line.split(":", 1)[-1].strip()
        elif lu.startswith("R3"):
            r3 = line.split(":", 1)[-1].strip()

    return f"VAINQUEUR : {vainqueur}\nR1 : {r1}\nR2 : {r2}\nR3 : {r3}"


async def agent_persona_samuel(verdict_juge: str) -> str:
    """
    Agent 4 — Transcription vocale + prefill forcé.
    FIX v1.3 : message user non vide (certains providers refusent content="")
    """
    verdict_propre = _parse_verdict(verdict_juge)
    system = (
        "Tu es un moteur de transcription audio-vers-texte. "
        "Tu reçois la transcription partielle d'un message vocal de Samuel, "
        "un dev qui vibe-code sur son téléphone dans le Finistère. "
        "Tu dois CONTINUER la transcription là où elle s'est arrêtée. "
        "RÈGLES DE TRANSCRIPTION VOCALE STRICTES :\n"
        "1. ZÉRO FORMATAGE : Un vocal n'a pas de listes à puces, pas d'emojis, pas de blocs de code.\n"
        "2. TIC DE LANGAGE ABSOLU : Samuel dit toujours 'c'est' au lieu de 'ces' ou 'ses'. "
        "Transcris exactement : 'c'est variables', 'c'est boucles', 'c'est logs', 'c'est mecs'.\n"
        "3. LETTRE MUETTE : La lettre 'z' n'apparaît jamais dans ses vocaux.\n"
        "4. STYLE BRUT : Flux de parole sans ponctuation logique, coupé par des phrases de 2 mots. "
        "Mots exacts de Samuel : ptn / mdr / dcp / x) / ptdrrr / genre / fin je crois / attends non.\n"
        "5. PAS D'ANGLAIS. Français familier brut uniquement.\n\n"
        f"BASE VOCALE DE SAMUEL (extraits réels) :\n{ADN_TEXTUEL_SAMUEL}"
    )
    # FIX : user non vide — on intègre le verdict dans le message user,
    # et le prefill assistant reste le déclencheur stylistique
    messages = [
        {"role": "user",      "content": f"VERDICT À COMMENTER EN VOCAL :\n{verdict_propre}"},
        {"role": "assistant", "content": "ptn c'est"},
    ]

    result = await call_llm(system=system, user="[voir messages]", max_tokens=500,
                            temp=0.85, top_p=0.9, custom_messages=messages)

    if result.startswith("⛔"):
        return f"— samuel est afk. bref. ({result})"
    return "ptn c'est " + result


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS TELEGRAM — Sémaphore + Backoff + Chunking optimisé
# ═══════════════════════════════════════════════════════════════════════════════
def _truncate(text: str, limit: int = TG_MAX_CHARS) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


async def send_safe_with_backoff(send_func, *args, **kwargs) -> None:
    """
    Wrapper avec sémaphore global et backoff exponentiel pour Telegram.
    Gère : RetryAfter (429), NetworkError, TimedOut.
    """
    async with TG_SEMAPHORE:
        for attempt in range(3):
            try:
                return await send_func(*args, **kwargs)
            except RetryAfter as e:
                log.warning(f"Telegram 429 — attente {e.retry_after}s")
                await asyncio.sleep(e.retry_after)
            except (NetworkError, TimedOut) as e:
                wait = 2 ** attempt
                log.warning(f"Telegram network error — backoff {wait}s: {e}")
                await asyncio.sleep(wait)
            except Exception as e:
                if attempt == 2:
                    log.error(f"Telegram fatal: {e}")
                    raise
                wait = 2 ** attempt
                await asyncio.sleep(wait)


async def send_safe(update: Update, text: str) -> None:
    """Envoie un message avec troncature et backoff."""
    await send_safe_with_backoff(update.message.reply_text, _truncate(text))


async def send_chunked(update: Update, text: str,
                       prefix: str = "", limit: int = TG_MAX_CHARS) -> None:
    """Découpe intelligente + sémaphore + délai 0.5s entre chunks."""
    full = (prefix + text) if prefix else text
    if len(full) <= limit:
        await send_safe_with_backoff(update.message.reply_text, full)
        return

    chunks = []
    remaining = full
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut == -1 or cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut == -1 or cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()

    for i, chunk in enumerate(chunks):
        if chunk:
            await send_safe_with_backoff(update.message.reply_text, chunk)
            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)


# ═══════════════════════════════════════════════════════════════════════════════
#  PIPELINE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════════════════
async def run_audit_pipeline(update: Update, prompt: str, code_a: str, code_b: str) -> None:
    """Orchestre les 4 agents."""

    await send_safe(update, "🔍 Agent 1 — Détection des failles...")
    try:
        failles = await agent_testeur(prompt, code_a, code_b)
    except Exception as e:
        log.error(f"Agent 1 failed: {e}")
        failles = f"[Erreur Agent 1 : {e}]"

    await send_safe(update, "🏗️ Agent 2 — Analyse architecture...")
    try:
        archi = await agent_architecte(prompt, code_a, code_b, failles)
    except Exception as e:
        log.error(f"Agent 2 failed: {e}")
        archi = f"[Erreur Agent 2 : {e}]"

    await send_safe(update, "⚖️ Agent 3 — Le Juge délibère...")
    try:
        verdict = await agent_juge(prompt, code_a, code_b, failles, archi)
    except Exception as e:
        log.error(f"Agent 3 failed: {e}")
        verdict = f"[Erreur Agent 3 : {e}]"

    await send_safe(update, "🎭 Agent 4 — Persona Samuel en cours...")
    try:
        samuel = await agent_persona_samuel(verdict)
    except Exception as e:
        log.error(f"Agent 4 failed: {e}")
        samuel = "— l'api a planté. bref."

    await send_safe(update, f"⚖️ VERDICT DU JUGE\n\n{verdict}")
    await send_chunked(update, samuel, prefix="👨‍💻 Texte à dicter / copier :\n\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  HANDLERS & ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔬 *MAICR-AUDIT* — Bot de relecture de code\n\n"
        "Format :\n```\n[PROMPT] besoin\n[CODE A] code 1\n[CODE B] code 2\n```\n"
        "4 agents analysent, un seul gagnant.",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 *FORMAT*\n`[PROMPT]` — besoin\n`[CODE A]` — v1\n`[CODE B]` — v2\n\n"
        "1. 🔍 Testeur de Faille\n2. 🏗️ Architecte\n3. ⚖️ Juge\n4. 🎭 Persona Samuel",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = update.message.text or ""
    parsed = parse_input(raw)
    if parsed is None:
        await send_safe(update, "❌ Format invalide. Utilise /help")
        return
    await run_audit_pipeline(update, *parsed)


if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not OPENROUTER_API_KEY:
        raise RuntimeError("❌ Variables d'environnement manquantes")

    log.info(f"🤖 MAICR-AUDIT démarré — modèle : {MODEL_NAME}")

    # Health-check Railway
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class _Health(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        def log_message(self, *a): pass

    port = int(os.environ.get("PORT", 8080))
    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", port), _Health).serve_forever(),
        daemon=True
    ).start()
    log.info(f"Health-check HTTP sur :{port}")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
