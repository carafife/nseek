#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nseek — découpe d'une ligne de Markdown en morceaux étiquetés.

Le chat affichait « **Sécurité** », « ## Fedora 45 », « *Change Proposals* »
tels quels : la mise en forme ne passait qu'après une réponse contenant un bloc
de code. Ici, la partie PURE (sans GTK) : une ligne → [(texte, étiquette)], les
étiquettes étant celles du TextBuffer (TAGS_DARK et TAGS_LIGHT dans nseek.py).

Volontairement simple : titres, gras, italique, code en ligne, puces. Pas de
tableaux ni de liens — du texte brut lisible vaut mieux qu'un rendu faux.
"""

import re

# Gras avant italique : « **a** » ne doit pas être lu comme deux italiques.
# Italique : une étoile collée au mot des deux côtés (« 2 * 3 * 4 » reste tel quel).
_MOTIF = re.compile(r'(\*\*[^*\n]+?\*\*|`[^`\n]+`|(?<![\w*])\*[^*\s][^*\n]*?(?<=\S)\*(?![\w*]))')


def segments(ligne):
    """Découpe une ligne. Renvoie une liste de (texte, étiquette)."""
    titre = re.match(r'^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$', ligne)
    if titre:
        return [(titre.group(1).replace("**", ""), "bold")]
    out = []
    puce = re.match(r'^(\s*)[-*+]\s+(?=\S)', ligne)
    if puce:
        out.append((puce.group(1) + "• ", "body"))
        ligne = ligne[puce.end():]
    for seg in _MOTIF.split(ligne):
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**") and len(seg) > 4:
            out.append((seg[2:-2], "bold"))
        elif seg.startswith("`") and seg.endswith("`") and len(seg) > 2:
            out.append((seg[1:-1], "code"))
        elif seg.startswith("*") and seg.endswith("*") and len(seg) > 2:
            out.append((seg[1:-1], "italic"))
        else:
            out.append((seg, "body"))
    return out
