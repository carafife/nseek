#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Nseek — RECHERCHE WEB (urllib seulement, sans dépendance, sans GTK).
#
# Nseek envoyait le texte tel quel à DeepSeek. Demande « à quoi s'attendre avec
# Fedora 45 ? » : réponse de mémoire (arrêtée avant 2026), fausse, puis
# « je n'ai pas d'accès Internet ». Ici, DeepSeek reçoit deux outils — chercher
# (web_search) et lire une page (web_fetch) — et décide seul de s'en servir.
#
# Moteurs, dans l'ordre, le premier qui répond gagne :
#   1. SearXNG LOCAL (127.0.0.1:8888) s'il tourne : il interroge Google, Bing…
#      depuis la connexion de l'utilisateur. Les moteurs ont fermé leurs API
#      (Bing arrêtée, Google Custom Search fermée aux nouveaux comptes).
#   2. Mojeek : index indépendant, sans clé. Toujours là.
#   3. DuckDuckGo : renvoie une page anti-robot depuis août 2026, gardé au cas où.
# Repris de web.py de Nseek Code, où chaque piège a été rencontré en vrai.
# ─────────────────────────────────────────────────────────────────────────────
import datetime
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

SEARXNG_URL = "http://127.0.0.1:8888"
MAX_TOURS = 6        # tours de recherche avant d'exiger une réponse

# Un vrai User-Agent : plusieurs moteurs répondent une page vide à un robot.
_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"


# ── Lecture de page ───────────────────────────────────────────────────────────
def _html_to_text(h):
    h = re.sub(r"(?is)<(script|style|head|nav|footer|svg|noscript).*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", h)
    return h.strip()


def fetch(url, max_chars=6000, timeout=20):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            raw = r.read(2_000_000)
    except urllib.error.HTTPError as e:
        return f"[HTTP {e.code} en récupérant {url}]"
    except Exception as e:
        return f"[Erreur récupération {url}: {e}]"
    text = raw.decode("utf-8", errors="replace")
    if "html" in ctype.lower() or text.lstrip()[:1] == "<":
        text = _html_to_text(text)
    text = text.strip()
    if not text:
        return "[Page vide ou non textuelle]"
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n… (tronqué à {max_chars} caractères)"
    return text


# ── Moteurs ───────────────────────────────────────────────────────────────────
def _get(url, timeout):
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "fr,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(1_000_000).decode("utf-8", errors="replace")


def searxng_ready(timeout=3):
    """Court exprès : si SearXNG est absent, on passe au suivant sans attendre."""
    try:
        req = urllib.request.Request(SEARXNG_URL + "/healthz", headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _searxng(query, max_results, timeout):
    url = SEARXNG_URL + "/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "language": "fr", "safesearch": 0})
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for it in data.get("results", []):
        u, t = it.get("url"), (it.get("title") or "").strip()
        if u and t:
            out.append((t, u, (it.get("content") or "").strip()))
        if len(out) >= max_results:
            break
    return out


def _mojeek(query, max_results, timeout):
    # urlencode (espaces en « + ») et NON quote (« %20 ») : Mojeek rend zéro
    # résultat sur les %20 dès qu'il y a plusieurs mots. Panne silencieuse.
    page = _get("https://www.mojeek.com/search?" + urllib.parse.urlencode({"q": query}),
                timeout)
    out = []
    for m in re.finditer(
            r'<a class="title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'(?:<p class="s">(.*?)</p>)?</li>', page, re.S):
        url = html.unescape(m.group(1))
        titre = _html_to_text(m.group(2))
        if titre and url.startswith("http"):
            out.append((titre, url, _html_to_text(m.group(3) or "")))
        if len(out) >= max_results:
            break
    return out


def _duckduckgo(query, max_results, timeout):
    page = _get("https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query}),
                timeout)
    out = []
    for m in re.finditer(r'<a\s+[^>]*href="([^"]*uddg=[^"]*)"[^>]*>(.*?)</a>', page, re.S):
        href = html.unescape(m.group(1))
        titre = _html_to_text(m.group(2)).strip()
        if not titre:
            continue
        if href.startswith("//"):
            href = "https:" + href
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        out.append((titre, q.get("uddg", [href])[0], ""))
        if len(out) >= max_results:
            break
    return out


def search(query, max_results=8, timeout=20):
    echecs = []
    moteurs = ([("SearXNG", _searxng)] if searxng_ready() else []) + \
              [("Mojeek", _mojeek), ("DuckDuckGo", _duckduckgo)]
    for nom, moteur in moteurs:
        try:
            res = moteur(query, max_results, timeout)
        except Exception as e:
            echecs.append(f"{nom} : {e}")
            continue
        if res:
            return "\n".join(f"{i}. {t}\n   {u}" + (f"\n   {x[:300]}" if x else "")
                             for i, (t, u, x) in enumerate(res, 1))
        echecs.append(f"{nom} : aucun résultat")
    return (f"[Recherche web indisponible pour « {query} » — " + " ; ".join(echecs) +
            ". DIS à l'utilisateur que tu n'as pas pu chercher plutôt que de deviner.]")


# ── Outils donnés au modèle ───────────────────────────────────────────────────
OUTILS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Recherche sur le web → titres + URLs. Pour une info récente, "
                       "une version, une date, un fait à vérifier.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Requête de recherche."}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "web_fetch",
        "description": "Lit le texte d'une page web. À utiliser sur une URL trouvée "
                       "via web_search.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL à lire."}},
            "required": ["url"]}}},
]


CONCLURE = ("Tu as fait assez de recherches. Réponds maintenant à l'utilisateur avec "
            "ce que tu as trouvé, sans appeler d'outil, en citant tes sources.")


def consigne(aujourd_hui=None):
    """À ajouter au message système. La DATE est essentielle : sans elle, le
    modèle croit vivre à sa date de coupure et juge « futur » ce qui est sorti."""
    jour = (aujourd_hui or datetime.date.today()).isoformat()
    return (f"Nous sommes le {jour}. Tu as accès au web avec web_search (recherche) "
            f"et web_fetch (lire une page). Tes connaissances s'arrêtent avant cette "
            f"date : pour toute information récente, datée, chiffrée ou à vérifier "
            f"(versions, sorties, actualité, prix), CHERCHE avant de répondre, et "
            f"cite les adresses de tes sources. Deux ou trois recherches suffisent "
            f"en général. Ne dis jamais que tu n'as pas accès "
            f"à Internet.")


def executer(nom, arguments):
    try:
        if nom == "web_search":
            q = (arguments.get("query") or "").strip()
            return search(q) if q else "[Erreur: paramètre 'query' manquant]"
        if nom == "web_fetch":
            u = (arguments.get("url") or "").strip()
            return fetch(u) if u else "[Erreur: paramètre 'url' manquant]"
        return f"[Erreur: outil inconnu '{nom}']"
    except Exception as e:
        return f"[Erreur outil {nom}: {e}]"


# ── Un tour d'API ─────────────────────────────────────────────────────────────
def lire_flux(lignes, on_text=None, on_reasoning=None, on_usage=None):
    """Lit un flux SSE DeepSeek (lignes en octets). Renvoie
    (texte, raisonnement, appels) où appels = [{id, name, arguments(str)}]."""
    texte, raisonnement, acc = [], [], {}
    for raw in lignes:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data: "):
            continue
        ds = line[6:]
        if ds == "[DONE]":
            break
        try:
            chunk = json.loads(ds)
        except Exception:
            continue
        u = chunk.get("usage")
        if u and u.get("prompt_tokens") and on_usage:
            on_usage(u)
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta", {})
        rc = delta.get("reasoning_content")
        if rc:
            raisonnement.append(rc)
            if on_reasoning:
                on_reasoning(rc)
        ct = delta.get("content")
        if ct:
            texte.append(ct)
            if on_text:
                on_text(ct)
        for tcd in delta.get("tool_calls") or []:
            slot = acc.setdefault(tcd.get("index", 0), {"id": "", "name": "", "arguments": ""})
            if tcd.get("id"):
                slot["id"] = tcd["id"]
            fn = tcd.get("function") or {}
            if fn.get("name"):
                slot["name"] = fn["name"]
            if fn.get("arguments"):
                slot["arguments"] += fn["arguments"]
    return "".join(texte), "".join(raisonnement), [acc[i] for i in sorted(acc)]


def _tour_api(api_url, key, body, stream, on_text, on_reasoning, on_usage):
    req = urllib.request.Request(
        api_url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        if stream:
            return lire_flux(r, on_text, on_reasoning, on_usage)
        d = json.load(r)
    if d.get("usage") and on_usage:
        on_usage(d["usage"])
    msg = d["choices"][0]["message"]
    appels = [{"id": tc.get("id", ""), "name": tc["function"].get("name", ""),
               "arguments": tc["function"].get("arguments") or ""}
              for tc in (msg.get("tool_calls") or [])]
    return msg.get("content") or "", msg.get("reasoning_content") or "", appels


def repondre(api_url, key, body, *, stream=True, on_text=None, on_reasoning=None,
             on_tool=None, on_usage=None, tour_api=_tour_api):
    """Fait répondre le modèle en le laissant chercher sur le web.

    `body` : le corps de requête habituel de Nseek (model, messages, thinking…),
    non modifié. Renvoie (texte final, raisonnement complet).
    on_tool(nom, arguments) est appelé avant chaque recherche, pour l'afficher.
    on_usage reçoit le dictionnaire « usage » de l'API à chaque tour.
    Les erreurs HTTP/réseau se propagent à l'appelant."""
    fil = list(body["messages"])
    pensees = []
    for tour in range(MAX_TOURS + 1):
        b = dict(body, messages=fil, stream=stream)
        if stream:
            b["stream_options"] = {"include_usage": True}
        b["tools"] = OUTILS
        if tour == MAX_TOURS:
            # Dernier tour : il faut conclure. On NE RETIRE PAS les outils — vu en
            # vrai : sans eux, le modèle (Réflexion cochée) écrit ses appels en
            # texte brut « <｜DSML｜calls>… », affichés tels quels. On les
            # interdit (tool_choice) et on le dit.
            b["tool_choice"] = "none"
            b["messages"] = fil + [{"role": "system", "content": CONCLURE}]
        texte, pensee, appels = tour_api(api_url, key, b, stream,
                                         on_text if stream else None,
                                         on_reasoning, on_usage)
        if pensee:
            pensees.append(pensee)
        if not appels:
            return texte, "\n".join(pensees)
        fil = fil + [{"role": "assistant", "content": texte, "tool_calls": [
            {"id": a["id"], "type": "function",
             "function": {"name": a["name"], "arguments": a["arguments"]}} for a in appels]}]
        for a in appels:
            try:
                args = json.loads(a["arguments"] or "{}")
                if not isinstance(args, dict):
                    raise ValueError
            except Exception:
                args = None
            if on_tool:
                on_tool(a["name"], args or {})
            resultat = (executer(a["name"], args) if args is not None else
                        "[Erreur : arguments illisibles, refais l'appel en JSON valide.]")
            fil.append({"role": "tool", "tool_call_id": a["id"], "content": resultat})
    return "", "\n".join(pensees)
