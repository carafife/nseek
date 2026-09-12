#!/usr/bin/env python3
"""Après un streaming, la réponse finale est mise en forme — et SEULEMENT elle.

Vécu en réel : en mode Chat, « **Sécurité** » et « ## Fedora 45 » restaient
bruts, car le re-rendu n'avait lieu que si la réponse contenait un bloc de code.
Et ce re-rendu effaçait tout depuis « 🤖 DeepSeek » : raisonnement et lignes
🔎 de recherche disparaissaient avec lui."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

import nseek as nseekcode


class _Muet:
    def __getattr__(self, _):
        return lambda *a, **k: None


def _fenetre():
    w = nseekcode.Win.__new__(nseekcode.Win)
    table = Gtk.TextTagTable()
    for nom, props in nseekcode.TAGS_DARK.items():
        tag = Gtk.TextTag(name=nom)
        for k, v in props.items():
            tag.set_property(k, v)
        table.add(tag)
    w.buf = Gtk.TextBuffer(tag_table=table)
    w.view = _Muet()
    w.history, w.session_name = [], "essai"
    w.status = w.send_btn = w.msg_tv = _Muet()
    w._refresh_sidebar = w._update_stats = lambda *a: None
    return w


def _tags_de(buf, mot):
    it = buf.get_start_iter()
    trouve = it.forward_search(mot, 0, None)
    assert trouve, f"« {mot} » absent de l'affichage"
    return {t.props.name for t in trouve[0].get_tags()}


def test_reponse_mise_en_forme_raisonnement_garde(monkeypatch):
    def faux_repondre(api_url, key, body, *, on_text, on_reasoning, on_tool, **_):
        on_reasoning("je dois chercher")
        on_tool("web_search", {"query": "fedora 45"})
        on_reasoning("j'ai trouvé")
        for morceau in ["## Fedora 45\n", "- **Sécu", "rité** : ptrace\n", "fin *ok*"]:
            on_text(morceau)
        return "…", ""

    monkeypatch.setattr(nseekcode.recherche, "repondre", faux_repondre)
    monkeypatch.setattr(nseekcode, "save_session", lambda *a, **k: None)
    w = _fenetre()
    w._call_stream("cle", "deepseek-v4-flash", True, [])

    ctx = GLib.MainContext.default()
    for _ in range(40):   # laisse passer les _drain (500 ms chacun)
        GLib.usleep(60_000)
        while ctx.pending():
            ctx.iteration(False)

    texte = w.buf.get_text(w.buf.get_start_iter(), w.buf.get_end_iter(), False)
    assert "**" not in texte and "## " not in texte, texte
    assert "je dois chercher" in texte and "🔎 Recherche : fedora 45" in texte
    assert texte.count("Sécurité") == 1, "la réponse ne doit pas être dupliquée"
    assert "bold" in _tags_de(w.buf, "Sécurité")
    assert "bold" in _tags_de(w.buf, "Fedora 45")
    assert "italic" in _tags_de(w.buf, "ok")
    assert w.history[-1]["content"].startswith("## Fedora 45")
