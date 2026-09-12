#!/usr/bin/env python3
"""Le Markdown du chat est mis en forme.

Vécu en réel : « **Sécurité / noyau** », « ## Fedora 45 » affichés avec leurs
étoiles et dièses. La mise en forme ne passait qu'après un bloc de code."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rendu_md import segments


def test_gras():
    assert segments("**Sécurité / noyau**") == [("Sécurité / noyau", "bold")]


def test_gras_au_milieu():
    assert segments("un **mot** ici") == [("un ", "body"), ("mot", "bold"), (" ici", "body")]


def test_titre():
    assert segments("## Fedora 45 (pas encore sortie)") == [("Fedora 45 (pas encore sortie)", "bold")]


def test_puce_avec_gras():
    assert segments("- **ptrace restreint** par défaut") == [
        ("• ", "body"), ("ptrace restreint", "bold"), (" par défaut", "body")]


def test_italique_et_code():
    assert segments("via des *Change Proposals* et `dnf5`") == [
        ("via des ", "body"), ("Change Proposals", "italic"), (" et ", "body"),
        ("dnf5", "code")]


def test_une_multiplication_nest_pas_de_litalique():
    assert segments("2 * 3 * 4") == [("2 * 3 * 4", "body")]


def test_ligne_vide_et_texte_simple():
    assert segments("") == []
    assert segments("rien de spécial") == [("rien de spécial", "body")]
