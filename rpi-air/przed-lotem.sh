#!/bin/bash
# Przed lotem, na RPi balonu:   bash ~/StratoSTEAM/rpi-air/przed-lotem.sh
#   bez argumentów — tylko pokazuje miejsce na karcie, filmy i dzienniki
#   --usun        — usuwa stare filmy i dzienniki (pyta o potwierdzenie)
#   --usun --tak  — to samo bez pytania
# Plików zmienianych w ostatnich 2 minutach nie rusza: to bieżący film i dziennik.
V=/home/admin/stratosteam-video
L=/home/admin/stratosteam-logi
GB_H=1.8        # tyle GB na godzinę filmu (4 Mbit/s)

show() {
    echo "== Karta RPi"; df -h / | tail -1 | awk '{print "   wolne: " $4 " z " $2 " (zajęte " $5 ")"}'
    for d in "$V" "$L"; do
        n=$(find "$d" -maxdepth 1 -type f 2>/dev/null | wc -l)
        s=$(du -sh "$d" 2>/dev/null | cut -f1)
        echo "   $d: $n plików, ${s:-0}"
    done
    free_gb=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
    awk -v f="$free_gb" -v r="$GB_H" 'BEGIN { printf "   starczy na ok. %.1f h filmu (film staje przy 1 GB wolnego, dziennik dalej działa)\n", (f - 1) / r }'
}

show
[ "$1" = "--usun" ] || exit 0
old=$(find "$V" "$L" -maxdepth 1 -type f \( -name 'rec_*.h264' -o -name 'lot_*' \) -mmin +2 2>/dev/null)
[ -n "$old" ] || { echo "Nie ma czego usuwać."; exit 0; }
echo; echo "Do usunięcia: $(echo "$old" | wc -l) plików, $(echo "$old" | tr '\n' '\0' | du -ch --files0-from=- | tail -1 | cut -f1)"
if [ "$2" != "--tak" ]; then
    read -r -p "Usunąć? Najpierw zgraj, co chcesz zachować! [t/N] " a
    [ "$a" = "t" ] || [ "$a" = "T" ] || { echo "Nic nie usunięto."; exit 0; }
fi
echo "$old" | tr '\n' '\0' | xargs -0 rm -f
echo; show
