Name:           nseek
Version:        1.0
Release:        1%{?dist}
Summary:        Client IA natif GTK4 pour DeepSeek V4

License:        GPL-3.0-or-later
URL:            https://github.com/carafife/nseek
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

# Dépendances requises à l'exécution
Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       gtksourceview5
Requires:       vte291-gtk4
Requires:       python3-cairosvg

# pypdf — nom peut varier selon la version de Fedora
Requires:       python3-pypdf

%description
Nseek est un client IA natif GTK4 pour Linux permettant d'interagir
avec l'API DeepSeek V4 directement depuis le bureau GNOME ou KDE.

Fonctionnalités :
- Chat IA en streaming temps réel avec mode Thinking
- Éditeur de code intégré avec coloration syntaxique (GtkSourceView 5)
- Terminal interactif (VTE) pour exécuter les scripts
- Historique des conversations sauvegardé localement
- Persona configurable et sélecteur de 10 langues
- Support des pièces jointes (texte, PDF)
- Thèmes clair et sombre
- Manuel utilisateur intégré

%prep
%autosetup

%install
# Répertoire principal de l'application
install -d %{buildroot}%{_datadir}/%{name}
install -d %{buildroot}%{_datadir}/%{name}/assets
install -d %{buildroot}%{_datadir}/%{name}/docs

# Fichiers Python
install -m 644 nseek.py     %{buildroot}%{_datadir}/%{name}/
install -m 644 make_logo.py %{buildroot}%{_datadir}/%{name}/

# Assets (logos et icônes)
install -m 644 assets/nseek-logo.png       %{buildroot}%{_datadir}/%{name}/assets/
install -m 644 assets/nseek-logo-ciel.png  %{buildroot}%{_datadir}/%{name}/assets/
install -m 644 assets/nseek-logo-marine.png %{buildroot}%{_datadir}/%{name}/assets/
install -m 644 assets/nseek-icon-ciel.png  %{buildroot}%{_datadir}/%{name}/assets/
install -m 644 assets/nseek-icon-ciel.svg  %{buildroot}%{_datadir}/%{name}/assets/
install -m 644 assets/nseek-icon-marine.svg %{buildroot}%{_datadir}/%{name}/assets/
install -m 644 assets/nseek-logo.svg       %{buildroot}%{_datadir}/%{name}/assets/
install -m 644 assets/nseek-icon-128.png   %{buildroot}%{_datadir}/%{name}/assets/
install -m 644 assets/nseek-icon-256.png   %{buildroot}%{_datadir}/%{name}/assets/
install -m 644 assets/nseek-icon-512.png   %{buildroot}%{_datadir}/%{name}/assets/

# Icônes système aux 3 tailles pour GNOME/KDE
install -d %{buildroot}%{_datadir}/icons/hicolor/128x128/apps
install -d %{buildroot}%{_datadir}/icons/hicolor/256x256/apps
install -d %{buildroot}%{_datadir}/icons/hicolor/512x512/apps
install -m 644 assets/nseek-icon-128.png \
    %{buildroot}%{_datadir}/icons/hicolor/128x128/apps/%{name}.png
install -m 644 assets/nseek-icon-256.png \
    %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/%{name}.png
install -m 644 assets/nseek-icon-512.png \
    %{buildroot}%{_datadir}/icons/hicolor/512x512/apps/%{name}.png

# Lanceur .desktop (intégration GNOME/KDE)
install -d %{buildroot}%{_datadir}/applications
install -m 644 nseek.desktop %{buildroot}%{_datadir}/applications/

# Métadonnées AppStream (GNOME Logiciels)
install -d %{buildroot}%{_datadir}/metainfo
install -m 644 nseek.metainfo.xml %{buildroot}%{_datadir}/metainfo/

# Script de lancement dans /usr/bin
install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/%{name} << 'EOF'
#!/bin/bash
exec python3 %{_datadir}/%{name}/nseek.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/%{name}

%post
# Mettre à jour le cache des icônes
/usr/bin/gtk-update-icon-cache -f -t %{_datadir}/icons/hicolor &>/dev/null || :

%postun
/usr/bin/gtk-update-icon-cache -f -t %{_datadir}/icons/hicolor &>/dev/null || :

%files
%license LICENSE
%doc README.md
%{_bindir}/%{name}
%{_datadir}/%{name}/
%{_datadir}/applications/%{name}.desktop
%{_datadir}/metainfo/%{name}.metainfo.xml
%{_datadir}/icons/hicolor/128x128/apps/%{name}.png
%{_datadir}/icons/hicolor/256x256/apps/%{name}.png
%{_datadir}/icons/hicolor/512x512/apps/%{name}.png

%changelog
* Sat May 09 2026 carafife <carafife@fedora> - 1.0-1
- Version initiale : chat IA GTK4, éditeur code VTE, Persona, 10 langues
- Terminal interactif VTE, coloration syntaxique GtkSourceView 5
- Thèmes clair/sombre, manuel utilisateur intégré
