#!/usr/bin/env python3
"""Nseek cherche sur le web.

Vécu en réel : « à quoi s'attendre avec Fedora 45 ? ». Réponse de mémoire,
fausse, puis « je n'ai pas d'accès Internet ». DeepSeek reçoit maintenant
web_search et web_fetch. Lancer : python3 -m pytest tests"""
import datetime
import json
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recherche


def _flux(*chunks):
    return [f"data: {json.dumps(c)}\n".encode() for c in chunks] + [b"data: [DONE]\n"]


def test_la_consigne_donne_la_date():
    """Sans la date, le modèle juge « futur » ce qui est déjà sorti."""
    c = recherche.consigne(datetime.date(2026, 9, 12))
    assert "2026-09-12" in c and "web_search" in c


def test_lire_flux_recolle_les_appels_fragmentes():
    lignes = _flux(
        {"choices": [{"delta": {"reasoning_content": "je cherche"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1",
            "function": {"name": "web_search", "arguments": '{"que'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0,
            "function": {"arguments": 'ry": "fedora"}'}}]}}]},
        {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 3}})
    usages = []
    texte, pensee, appels = recherche.lire_flux(lignes, on_usage=usages.append)
    assert texte == "" and pensee == "je cherche"
    assert appels == [{"id": "c1", "name": "web_search", "arguments": '{"query": "fedora"}'}]
    assert usages == [{"prompt_tokens": 10, "completion_tokens": 3}]


class FausseAPI:
    def __init__(self, tours):
        self.tours, self.corps = list(tours), []

    def __call__(self, url, key, body, stream, on_text, on_reasoning, on_usage):
        self.corps.append(body)
        texte, appels = self.tours.pop(0)
        if texte and on_text:
            on_text(texte)
        return texte, "", appels


def test_recherche_puis_reponse(monkeypatch):
    monkeypatch.setattr(recherche, "search", lambda q: f"RÉSULTATS {q}")
    api = FausseAPI([
        ("", [{"id": "c1", "name": "web_search", "arguments": '{"query": "fedora 45"}'}]),
        ("Sortie le 20 octobre.", []),
    ])
    body = {"model": "x", "messages": [{"role": "user", "content": "q"}]}
    vus, texte = [], []
    r, _ = recherche.repondre("u", "k", body, tour_api=api, on_text=texte.append,
                              on_tool=lambda n, a: vus.append((n, a)))
    assert r == "Sortie le 20 octobre." and texte == [r]
    assert vus == [("web_search", {"query": "fedora 45"})]
    fil = api.corps[1]["messages"]
    assert fil[1]["tool_calls"][0]["id"] == "c1"
    assert fil[2] == {"role": "tool", "tool_call_id": "c1", "content": "RÉSULTATS fedora 45"}
    # Le corps de l'appelant n'est pas touché : l'historique sauvé reste propre.
    assert body == {"model": "x", "messages": [{"role": "user", "content": "q"}]}


def test_le_dernier_tour_interdit_les_outils_sans_les_retirer(monkeypatch):
    """Vu en vrai : outils RETIRÉS au dernier tour → le modèle écrit ses appels
    en texte brut « <｜DSML｜calls>… », affichés à l'utilisateur."""
    monkeypatch.setattr(recherche, "search", lambda q: "r")
    appel = [{"id": "c", "name": "web_search", "arguments": '{"query": "q"}'}]
    api = FausseAPI([("", appel)] * recherche.MAX_TOURS + [("fin", [])])
    r, _ = recherche.repondre("u", "k", {"model": "x", "messages": []}, tour_api=api)
    assert r == "fin"
    dernier = api.corps[-1]
    assert dernier["tools"] and dernier["tool_choice"] == "none"
    assert dernier["messages"][-1]["content"] == recherche.CONCLURE
    assert all("tool_choice" not in c for c in api.corps[:-1])


def test_arguments_illisibles_ne_plantent_pas():
    api = FausseAPI([("", [{"id": "c", "name": "web_search", "arguments": '{"query'}]),
                     ("ok", [])])
    r, _ = recherche.repondre("u", "k", {"model": "x", "messages": []}, tour_api=api)
    assert r == "ok"
    assert "illisibles" in api.corps[1]["messages"][-1]["content"]
