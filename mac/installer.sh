#!/bin/bash
# Padel libre — partie Mac : récupère Playtomic (qui refuse les serveurs GitHub)
# toutes les 15 min et l'envoie dans le dépôt. À lancer une seule fois :
#   bash <(curl -fsSL https://raw.githubusercontent.com/hector347321/padel-dispo/main/mac/installer.sh)
# Désinstaller :
#   launchctl unload ~/Library/LaunchAgents/ch.padel.playtomic.plist; rm -rf ~/Library/LaunchAgents/ch.padel.playtomic.plist ~/padel-dispo-mac ~/.padel-dispo.json
set -e
REPO="hector347321/padel-dispo"
DIR="$HOME/padel-dispo-mac"
CONF="$HOME/.padel-dispo.json"
PLIST="$HOME/Library/LaunchAgents/ch.padel.playtomic.plist"
mkdir -p "$DIR" "$HOME/Library/LaunchAgents"

echo "Padel libre : installation de la partie Mac"
if [ ! -f "$CONF" ]; then
  echo
  echo "Colle ton jeton GitHub (le même que sur l'iPhone, github_pat_…), puis Entrée :"
  read -rs TOKEN
  echo
  read -rp "Sujet ntfy pour les notifications [padel-7cf8659e0a] : " NTFY
  NTFY="${NTFY:-padel-7cf8659e0a}"
  printf '{"token": "%s", "ntfy": "%s"}\n' "$TOKEN" "$NTFY" > "$CONF"
  chmod 600 "$CONF"
fi

# Le script récupère toujours la dernière version du collecteur avant de tourner
cat > "$DIR/run.sh" <<EOF
#!/bin/bash
cd "$DIR"
curl -fsSL "https://raw.githubusercontent.com/$REPO/main/collect.py" -o collect.py.new && mv collect.py.new collect.py
/usr/bin/python3 collect.py --mac
EOF
chmod +x "$DIR/run.sh"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ch.padel.playtomic</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/run.sh</string></array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/log.txt</string>
  <key>StandardErrorPath</key><string>$DIR/log.txt</string>
</dict></plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Premier passage en cours…"
sleep 25
tail -8 "$DIR/log.txt" 2>/dev/null || true
echo
echo "Installé. Ton Mac envoie Playtomic toutes les 15 min (quand il est allumé)."
