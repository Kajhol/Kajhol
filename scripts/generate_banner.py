"""Generator animowanego banera do README profilu (assets/banner.svg).

Baner to mapa topograficzna (poziomice liczone algorytmem marching squares
z syntetycznego pola wysokości), pisany tekst i robot, który siedzi przy
komputerze, klepie w klawiaturę, a co jakiś czas obraca się do widza i coś mówi.
GitHub nie wykonuje JavaScriptu w README, więc cała animacja to CSS + SMIL
wewnątrz pliku SVG.

Uruchomienie (z katalogu repo):  python scripts/generate_banner.py
Podgląd: otwórz assets/banner.svg w przeglądarce.
"""

from pathlib import Path
from xml.sax.saxutils import escape  # „&” w tekście musi trafić do SVG jako „&amp;”

import numpy as np

W, H = 1200, 340
STEP = 5  # rozdzielczość siatki w pikselach

# Paleta wzięta ze zdjęcia profilowego: granat koszulki, biel i błękit nadruku,
# ciepły ceglasty pomarańcz tła. Do tego miętowy kiełek robota.
BG0, BG1 = "#080f24", "#15214a"
CONTOUR = "#7f9cd6"
ACCENT = "#a9c8ff"
WARM = "#ef8a5a"
MINT = "#8fe3b0"
# Kolory logo Kodies
K_DARK, K_BLUE = "#1f2630", "#0b6cff"
TEXT = "#f5f7fb"
MUTED = "#7d8fb8"
SHELL, LIMB, VISOR, SCREEN = "#1f3263", "#18284f", "#060c1d", "#0b1633"

MONO = "Consolas, 'DejaVu Sans Mono', Menlo, 'Courier New', monospace"
SANS = "'Segoe UI', 'Helvetica Neue', Ubuntu, Arial, sans-serif"

SUBTITLES = [
    "Software Engineer & AI Automation Enthusiast",
    "CS student @ Silesian University of Technology",
    "Building AI tools that optimize workflows",
]

# Teksty w dymku — jeden na każde odwrócenie się robota, w nieskończonej pętli
ROBOT_LINES = [
    "hello, human!",
    "01101000 01101001",  # „hi” w ASCII, binarnie
    "beep boop. welcome!",
    "while (alive) learn();",
    "scanning terrain...",
    'git commit -m "hi"',
    "check out my repos ↓",
]

# Scena (biurko + robot) rysowana jest we własnym układzie: (0, 0) = miejsce,
# w którym robot siedzi na stołku. Potem cała scena jest przesuwana i skalowana.
SCENE_POS = (760, 255, 1.25)  # x, y, skala

# Oś czasu jednego cyklu robota (sekundy)
CYCLE = 6.5   # długość cyklu
T1 = 2.5      # koniec pisania — obrót do widza
TURN = 0.3    # czas obrotu
T2 = 6.2      # koniec gadania — obrót z powrotem do komputera


def pct(t):
    """Czas w cyklu → procent w @keyframes."""
    return f"{t / CYCLE * 100:.2f}%"


# --- Pole wysokości -----------------------------------------------------------

def height_field():
    """Suma „górek” Gaussa + łagodny szum, żeby poziomice nie były idealnymi elipsami."""
    xs = np.arange(0, W + 1, STEP, dtype=float)
    ys = np.arange(0, H + 1, STEP, dtype=float)
    x, y = np.meshgrid(xs, ys)

    def hill(cx, cy, sx, sy, amp):
        return amp * np.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))

    h = (
        hill(905, 165, 165, 115, 1.00)   # główny szczyt
        + hill(1115, 60, 110, 85, 0.62)
        + hill(700, 345, 150, 80, 0.42)
        + hill(1060, 315, 70, 60, 0.34)
        + hill(110, 400, 230, 110, 0.38)  # łagodne zbocze pod tekstem
    )
    h += 0.045 * np.sin(x / 37 + y / 53) + 0.035 * np.sin(x / 23 - y / 31)
    return h


# --- Marching squares ---------------------------------------------------------

# Dla każdego z 16 przypadków: pary krawędzi komórki, które łączy odcinek.
# Krawędzie: T(góra), R(prawo), B(dół), L(lewo). Przypadki 5 i 10 (siodła)
# rozstrzygane osobno na podstawie średniej w środku komórki.
CASES = {
    1: [("L", "B")], 2: [("B", "R")], 3: [("L", "R")], 4: [("T", "R")],
    6: [("T", "B")], 7: [("T", "L")], 8: [("T", "L")], 9: [("T", "B")],
    11: [("T", "R")], 12: [("L", "R")], 13: [("B", "R")], 14: [("L", "B")],
}


def edge_key(j, i, e):
    """Unikalny klucz krawędzi siatki — sąsiednie komórki współdzielą klucze."""
    return {"T": (j, i, "h"), "B": (j + 1, i, "h"), "L": (j, i, "v"), "R": (j, i + 1, "v")}[e]


def edge_point(h, key, level):
    """Interpolacja liniowa: gdzie na krawędzi pole przyjmuje wartość `level`."""
    j, i, kind = key
    a = h[j, i]
    b = h[j, i + 1] if kind == "h" else h[j + 1, i]
    t = (level - a) / (b - a)
    return ((i + t) * STEP, j * STEP) if kind == "h" else (i * STEP, (j + t) * STEP)


def contours(h, level):
    ny, nx = h.shape
    segments = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            tl, tr, br, bl = h[j, i], h[j, i + 1], h[j + 1, i + 1], h[j + 1, i]
            idx = (tl > level) << 3 | (tr > level) << 2 | (br > level) << 1 | (bl > level)
            if idx in (0, 15):
                continue
            if idx in (5, 10):
                center_up = (tl + tr + br + bl) / 4 > level
                if (idx == 5) == center_up:
                    pairs = [("T", "L"), ("B", "R")]
                else:
                    pairs = [("T", "R"), ("L", "B")]
            else:
                pairs = CASES[idx]
            for e1, e2 in pairs:
                segments.append((edge_key(j, i, e1), edge_key(j, i, e2)))

    # Sklejanie odcinków w łamane: każdy punkt krawędzi należy do ≤ 2 odcinków.
    by_point = {}
    for n, (a, b) in enumerate(segments):
        by_point.setdefault(a, []).append(n)
        by_point.setdefault(b, []).append(n)

    used = [False] * len(segments)
    lines = []

    def walk(start_seg, start_pt):
        chain = [start_pt]
        seg, pt = start_seg, start_pt
        while True:
            used[seg] = True
            a, b = segments[seg]
            pt = b if a == pt else a
            chain.append(pt)
            nxt = [s for s in by_point[pt] if not used[s]]
            if not nxt:
                return chain
            seg = nxt[0]

    # Najpierw linie otwarte (zaczynają się na brzegu mapy), potem zamknięte pętle.
    for pt, segs in by_point.items():
        if len(segs) == 1 and not used[segs[0]]:
            lines.append(walk(segs[0], pt))
    for n in range(len(segments)):
        if not used[n]:
            lines.append(walk(n, segments[n][0]))

    return [[edge_point(h, k, level) for k in line] for line in lines]


# --- Wygładzanie i upraszczanie łamanych --------------------------------------

def chaikin(pts, closed):
    """Jedna iteracja algorytmu Chaikina: ścina narożniki, łamana robi się gładka."""
    out = [] if closed else [pts[0]]
    for k in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[k], pts[k + 1]
        out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1),
                (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
    out.append(out[0] if closed else pts[-1])
    return out


def rdp(pts, eps):
    """Ramer–Douglas–Peucker: usuwa punkty, które prawie nie zmieniają kształtu."""
    if len(pts) < 3:
        return pts
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    norm = (dx * dx + dy * dy) ** 0.5 or 1e-9
    dists = [abs(dy * (x - x0) - dx * (y - y0)) / norm for x, y in pts[1:-1]]
    k = int(np.argmax(dists)) + 1
    if dists[k - 1] <= eps:
        return [pts[0], pts[-1]]
    return rdp(pts[: k + 1], eps)[:-1] + rdp(pts[k:], eps)


def to_path(pts):
    fmt = lambda v: f"{v:.1f}".rstrip("0").rstrip(".")
    closed = len(pts) > 2 and pts[0] == pts[-1]
    if len(pts) > 2:
        pts = chaikin(chaikin(pts, closed), closed)
    pts = rdp(pts, 0.35)
    d = "M" + " L".join(f"{fmt(x)},{fmt(y)}" for x, y in pts)
    return d + ("Z" if closed else "")


# --- Pisany tekst (SMIL, krok co znak) ----------------------------------------

def typing_timelines(texts, x0, char_w, slot, offset=0.0, window=None,
                     dt_type=0.05, dt_erase=0.016):
    """Tekst nr i pisze się od chwili i*slot + offset, stoi i kasuje się przed
    upływem `window` sekund.

    Zwraca (czas pętli, [klatki szerokości maski dla każdego tekstu], klatki pozycji kursora).
    """
    window = window or slot
    total = round(slot * len(texts), 3)
    lines, cursor = [], [(0.0, x0)]
    for n_line, text in enumerate(texts):
        n = len(text)
        s = n_line * slot + offset
        erase_start = s + window - n * dt_erase - 0.2
        frames = [(0.0, 0.0)]
        frames += [(s + k * dt_type, k * char_w) for k in range(n + 1)]
        frames += [(erase_start + (n - k) * dt_erase, k * char_w) for k in range(n, -1, -1)]
        frames = sorted({round(t, 3): w for t, w in frames}.items())
        lines.append(frames)
        cursor += [(t, x0 + w) for t, w in frames if t > 0]
    cursor = sorted({round(t, 3): x for t, x in cursor}.items())
    return total, lines, cursor


def smil(attr, frames, total, begin="0s"):
    values = ";".join(f"{v:.1f}" for _, v in frames)
    times = ";".join(f"{t / total:.4f}" for t, _ in frames)
    return (f'<animate attributeName="{attr}" dur="{total}s" begin="{begin}" '
            f'repeatCount="indefinite" calcMode="discrete" values="{values}" keyTimes="{times}"/>')


def typed_lines(texts, x0, y, font_size, slot, begin, prefix, cursor_cls,
                offset=0.0, window=None):
    """Pisane linie tekstu w jednym miejscu: maska (clipPath) odsłania tekst znak po znaku,
    kursor jedzie za ostatnim znakiem. Czcionka monospace, więc znak = 0.6 em."""
    char_w = font_size * 0.6
    total, frames_per_line, cursor_frames = typing_timelines(
        texts, x0, char_w, slot, offset, window)
    out = []
    for n, (text, frames) in enumerate(zip(texts, frames_per_line)):
        out.append(
            f'<clipPath id="{prefix}{n}"><rect x="{x0}" y="{y - font_size * 1.2:.0f}" '
            f'height="{font_size * 1.7:.0f}" width="0">{smil("width", frames, total, begin)}</rect></clipPath>'
            f'<text x="{x0}" y="{y}" class="{prefix}" clip-path="url(#{prefix}{n})" '
            f'textLength="{len(text) * char_w:.1f}" lengthAdjust="spacing">{escape(text)}</text>'
        )
    out.append(
        f'<rect x="{x0}" y="{y - font_size * 0.95:.0f}" width="{char_w * 0.9:.0f}" '
        f'height="{font_size * 1.2:.0f}" class="{cursor_cls}">{smil("x", cursor_frames, total, begin)}</rect>'
    )
    return "".join(out)


# --- Scena: biurko i robot ----------------------------------------------------

def noodle(d, width=9, cls=""):
    """Giętka kończyna: gruba linia w kolorze obrysu + węższa w kolorze wypełnienia."""
    c = f' class="{cls}"' if cls else ""
    return (f'<g{c}><path d="{d}" fill="none" stroke="{ACCENT}" stroke-width="{width + 4}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{d}" fill="none" stroke="{LIMB}" stroke-width="{width}" '
            f'stroke-linecap="round" stroke-linejoin="round"/></g>')


def antenna(x):
    """Antenka na czubku głowy: lekko wygięta, sprężynuje wokół nasady, czubek pulsuje."""
    return f"""
          <g class="antenna" style="transform-origin:{x}px -142px">
            <path d="M{x},-142 C{x},-154 {x - 4},-160 {x - 2},-171" fill="none" stroke="{ACCENT}" stroke-width="3" stroke-linecap="round"/>
            <circle class="tip" cx="{x - 2}" cy="-176" r="6" fill="{WARM}" filter="url(#glow)"/>
          </g>
          <rect x="{x - 7}" y="-146" width="14" height="6" rx="3" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/>"""


def kd_logo(x, y, s, k_color, d_color, opacity=1.0):
    """Monogram KD z logo Kodies (odrysowany ze współrzędnych obrazka; pudełko 64.4 × 45.7).
    K w kolorze `k_color`, D i nawiasy < > w kolorze `d_color`."""
    return f"""
        <g transform="translate({x},{y}) scale({s})" opacity="{opacity}">
          <path d="M0,0 H9.3 V13.7 L0,22.4Z M0,25.2 L25.4,0 H36.5 L14.3,21.6 L36.5,45.7 H25.2 L8.4,27.6 V45.7 H0Z" fill="{k_color}"/>
          <path d="M39.9,0 H43.3 A21.1,22.85 0 0 1 43.3,45.7 H39.9 L32.9,37.9 H43.3 A13.7,15.05 0 0 0 43.3,7.8 H32.5Z" fill="{d_color}"/>
          <path d="M33.3,14.3 L25.3,23.2 L33.3,32.1 M41.8,14.3 L49.8,23.2 L41.8,32.1" fill="none" stroke="{d_color}"
                stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>
        </g>"""


def mug(x, y):
    """Kubek z logo nadrukowanym ton w ton — (x, y) = lewy dolny róg kubka."""
    w, h = 26, 30
    return f"""
    <path d="M{x + w - 1},{y - h + 8} q11,0 11,9 q0,9 -11,9" fill="none" stroke="{ACCENT}" stroke-width="2.5"/>
    <rect x="{x}" y="{y - h}" width="{w}" height="{h}" rx="4" fill="{SHELL}" stroke="{ACCENT}" stroke-width="2"/>
    <rect x="{x + 3}" y="{y - h + 3}" width="3" height="{h - 6}" rx="1.5" fill="#fff" opacity=".07"/>
    {kd_logo(x + 4.5, y - h / 2 - 6, 0.27, "#4d68b3", "#3f7ae6", 0.9)}
    <path class="steam" d="M{x + 8},{y - h - 6} q-4,-6 0,-12 q4,-6 0,-12" fill="none" stroke="{MUTED}" stroke-width="2" stroke-linecap="round"/>
    <path class="steam" style="animation-delay:-1.2s" d="M{x + 17},{y - h - 6} q-4,-6 0,-12 q4,-6 0,-12" fill="none" stroke="{MUTED}" stroke-width="2" stroke-linecap="round"/>"""


# Tułów: zaokrąglony trapez — szerszy w barkach, węższy w pasie
TORSO_FRONT = ("M-30,-72 Q-35,-72 -34,-66 L-27,-8 Q-26,-2 -20,-2 H20 Q26,-2 27,-8 "
               "L34,-66 Q35,-72 30,-72Z")
TORSO_SIDE = ("M-21,-72 H19 Q27,-72 27,-64 L23,-8 Q22,-2 16,-2 H-16 Q-22,-2 -23,-8 "
              "L-27,-64 Q-27,-72 -21,-72Z")


def desk():
    """Stołek, biurko, klawiatura, monitor z pisanym kodem i kubek z parą."""
    line = f'stroke="{ACCENT}" stroke-width="2"'
    # Linijki „kodu” na ekranie: (wcięcie, szerokość, kolor)
    code = [(0, 70, ACCENT), (10, 46, WARM), (10, 82, MUTED), (20, 58, ACCENT),
            (20, 36, MINT), (10, 64, MUTED), (0, 28, WARM), (0, 90, ACCENT)]
    code_svg = "".join(
        f'<rect class="code code{i}" x="{163 + ind}" y="{-128 + i * 10}" width="{w}" height="5" rx="2.5" fill="{c}"/>'
        for i, (ind, w, c) in enumerate(code)
    )
    keys = "".join(f'<rect x="{67 + k * 9}" y="-27" width="6" height="2.5" rx="1" fill="{MUTED}"/>'
                   for k in range(8))
    return f"""
    <ellipse cx="120" cy="57" rx="230" ry="7" fill="#000" opacity=".25"/>
    <!-- stołek -->
    <rect x="-4" y="8" width="8" height="44" fill="{LIMB}" {line}/>
    <ellipse cx="0" cy="54" rx="22" ry="4" fill="{LIMB}" {line}/>
    <ellipse cx="0" cy="5" rx="30" ry="6" fill="{SHELL}" {line}/>
    <!-- biurko -->
    <rect x="55" y="-12" width="8" height="68" fill="{LIMB}" {line}/>
    <rect x="313" y="-12" width="8" height="68" fill="{LIMB}" {line}/>
    <rect x="40" y="-22" width="296" height="10" rx="4" fill="{SHELL}" {line}/>
    <!-- klawiatura -->
    <rect x="62" y="-29" width="80" height="7" rx="2" fill="{LIMB}" stroke="{ACCENT}" stroke-width="1.5"/>
    {keys}
    <!-- monitor -->
    <rect x="212" y="-40" width="16" height="12" fill="{LIMB}" {line}/>
    <rect x="190" y="-29" width="60" height="7" rx="3" fill="{SHELL}" {line}/>
    <rect x="145" y="-146" width="150" height="106" rx="10" fill="{VISOR}" stroke="{ACCENT}" stroke-width="2.5"/>
    <rect x="155" y="-136" width="130" height="86" rx="4" fill="{SCREEN}"/>
    {code_svg}
    <rect x="163" y="-58" width="6" height="7" fill="{ACCENT}" class="blink"/>
    <!-- kubek z parą -->
    {mug(299, -22)}"""


def robot_side():
    """Robot z boku, przodem do monitora (w prawo), pisze na klawiaturze."""
    shell = f'fill="{SHELL}" stroke="{ACCENT}" stroke-width="2.5"'
    return f"""
    <g class="side">
      {noodle("M4,-2 L26,0 L30,28", 8, "dangle-far")}
      {noodle("M4,-56 C34,-46 64,-34 96,-35", 7, "type-far")}
      <circle cx="96" cy="-35" r="6" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2" class="type-far"/>
      <g class="lean">
        <rect x="-6" y="-86" width="12" height="16" rx="3" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/>
        <path d="{TORSO_SIDE}" {shell}/>
        <g class="nod">
          <rect x="-34" y="-142" width="76" height="60" rx="26" {shell}/>
          <rect x="14" y="-128" width="24" height="30" rx="10" fill="{VISOR}"/>
          <rect x="25" y="-120" width="7" height="11" rx="2" fill="{ACCENT}" filter="url(#glow)" class="eye"/>
          <circle cx="-6" cy="-112" r="9" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/>
          <circle cx="-6" cy="-112" r="3" fill="{ACCENT}"/>
          {antenna(4)}
        </g>
      </g>
      {noodle("M2,-2 L26,2 L32,30", 9, "dangle")}
      <ellipse cx="37" cy="32" rx="9" ry="5" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2" class="dangle"/>
      {noodle("M8,-54 C34,-40 56,-30 78,-34", 8, "type-near")}
      <circle cx="78" cy="-34" r="7" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2" class="type-near"/>
    </g>"""


def robot_front():
    """Robot przodem do widza: macha, mówi, oczy jak ^ ^."""
    shell = f'fill="{SHELL}" stroke="{ACCENT}" stroke-width="2.5"'
    # „Equalizer” na piersi — jak w pierwszej wersji robota
    bars = "".join(
        f'<rect class="bar" x="{x}" y="-54" width="6" height="17" rx="2" fill="{c}" '
        f'style="animation-duration:{d}s;animation-delay:-{d / 2:.2f}s"/>'
        for x, c, d in [(-15, WARM, .7), (-6, ACCENT, .9), (3, WARM, .6), (12, ACCENT, 1.1)]
    )
    return f"""
    <g class="front">
      <g class="kickL">{noodle("M-12,-2 L-14,30", 8)}<ellipse cx="-16" cy="32" rx="9" ry="5" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/></g>
      <g class="kickR">{noodle("M12,-2 L14,30", 8)}<ellipse cx="16" cy="32" rx="9" ry="5" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/></g>
      {noodle("M-28,-62 C-44,-48 -42,-26 -30,-16", 8)}
      <circle cx="-30" cy="-16" r="7" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/>
      <rect x="-7" y="-86" width="14" height="16" rx="3" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/>
      <path d="{TORSO_FRONT}" {shell}/>
      <rect x="-21" y="-60" width="42" height="28" rx="7" fill="{VISOR}"/>
      {bars}
      <g class="hi">
        {noodle("M28,-62 C48,-66 62,-76 72,-94", 8)}
        <circle cx="73" cy="-97" r="7" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/>
      </g>
      <rect x="-48" y="-124" width="12" height="24" rx="5" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/>
      <rect x="36" y="-124" width="12" height="24" rx="5" fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"/>
      <rect x="-40" y="-142" width="80" height="60" rx="26" {shell}/>
      <rect x="-30" y="-132" width="60" height="38" rx="14" fill="{VISOR}"/>
      <path d="M-19,-110 l6,-7 l6,7 M7,-110 l6,-7 l6,7" fill="none" stroke="{ACCENT}" stroke-width="3"
            stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)"/>
      <rect x="-5" y="-104" width="10" height="4" rx="2" fill="{WARM}" class="mouth"/>
      {antenna(0)}
    </g>"""


def bubble():
    """Dymek z tekstem — widoczny tylko, gdy robot patrzy na widza."""
    sx, sy, ss = SCENE_POS
    say_fs, pad = 14, 16
    bx1, by0, by1 = sx - 68, 52, 92
    bx0 = bx1 - 2 * pad - max(len(t) for t in ROBOT_LINES) * say_fs * 0.6 - 10
    tip = (sx - 44 * ss, sy - 112 * ss)  # lewy bok głowy (widok z przodu)
    path = (f"M{bx0 + 14:.0f},{by0} H{bx1 - 14} Q{bx1},{by0} {bx1},{by0 + 14} V{by1 - 14} "
            f"Q{bx1},{by1} {bx1 - 14},{by1} H{bx1 - 16} L{tip[0]:.0f},{tip[1]:.0f} "
            f"L{bx1 - 36},{by1} H{bx0 + 14:.0f} Q{bx0:.0f},{by1} {bx0:.0f},{by1 - 14} V{by0 + 14} "
            f"Q{bx0:.0f},{by0} {bx0 + 14:.0f},{by0}Z")
    # Każdy tekst pisze się w „swoim” cyklu, zaraz po obrocie do widza
    said = typed_lines(ROBOT_LINES, round(bx0 + pad), by0 + 25, say_fs, CYCLE, "0s",
                       "say", "blink say-cursor",
                       offset=T1 + TURN + 0.15, window=T2 - T1 - TURN - 0.3)
    return f"""
  <g class="bubble" style="transform-origin:{tip[0]:.0f}px {tip[1]:.0f}px">
    <path d="{path}" fill="{BG0}" fill-opacity=".85" stroke="{ACCENT}" stroke-width="1.5"/>
    {said}
  </g>"""


def scene_css():
    """Animacje sceny. Wszystkie pętle robota mają długość CYCLE, więc są zsynchronizowane
    z dymkiem (SMIL), który też zaczyna się w chwili 0."""
    e = 0.01  # „natychmiastowa” zmiana: dwie klatki kluczowe odległe o 0.01 s
    m1, m2 = T1 + TURN / 2, T2 + TURN / 2  # środki obrotów — wtedy podmiana rysunku
    step = (T1 - 0.2) / 8  # 8 linijek kodu musi się zmieścić w czasie pisania
    code_kf = "".join(
        f"@keyframes code{i} {{ 0%, {pct(0.1 + i * step)} {{ transform: scaleX(0); }} "
        f"{pct(0.1 + (i + 0.9) * step)}, {pct(T2 + 0.15)} {{ transform: scaleX(1); }} "
        f"{pct(T2 + 0.25)}, 100% {{ transform: scaleX(0); }} }}\n  "
        f".code{i} {{ animation-name: code{i}; }}\n  "
        for i in range(8)
    )
    return f"""
  .code {{ transform-box: fill-box; transform-origin: left; transform: scaleX(0);
          animation: {CYCLE}s steps(6, end) infinite; }}
  {code_kf}
  .spin, .side, .front, .bubble, .antenna, .lean, .nod, .dangle, .dangle-far,
  .type-near, .type-far, .hi, .kickL, .kickR {{ transform-box: view-box; }}
  .spin {{ animation: spin {CYCLE}s ease-in-out infinite; }}
  .side {{ animation: show-side {CYCLE}s linear infinite; }}
  .front {{ opacity: 0; animation: show-front {CYCLE}s linear infinite; }}
  .bubble {{ opacity: 0; animation: bubble {CYCLE}s ease-out infinite; }}
  .type-near {{ transform-origin: 8px -54px; animation: tap .16s ease-in-out infinite alternate; }}
  .type-far {{ transform-origin: 4px -56px; animation: tap .16s ease-in-out -.08s infinite alternate; }}
  .lean {{ transform-origin: 0 0; transform: rotate(6deg); }}
  .bar {{ transform-box: fill-box; transform-origin: bottom; animation: eq ease-in-out infinite alternate; }}
  @keyframes eq {{ from {{ transform: scaleY(.25); }} to {{ transform: scaleY(1); }} }}
  .nod {{ transform-origin: 0 -80px; animation: nod .9s ease-in-out infinite alternate; }}
  .dangle {{ transform-origin: 26px 0; animation: dangle 1.4s ease-in-out infinite alternate; }}
  .dangle-far {{ transform-origin: 26px 0; animation: dangle 1.4s ease-in-out -.7s infinite alternate; }}
  .kickL {{ transform-origin: -12px -2px; animation: kick 1.2s ease-in-out infinite alternate; }}
  .kickR {{ transform-origin: 12px -2px; animation: kick 1.2s ease-in-out -.6s infinite alternate; }}
  .hi {{ transform-origin: 28px -62px; animation: hi .45s ease-in-out infinite alternate; }}
  .antenna {{ animation: boing 1.3s ease-in-out infinite alternate; }}
  .tip {{ animation: pulse 1.6s ease-in-out infinite; }}
  .mouth {{ transform-box: fill-box; transform-origin: center; animation: talk .18s steps(2) infinite alternate; }}
  .eye {{ transform-box: fill-box; transform-origin: center; animation: blink-eye 3.5s infinite; }}
  .steam {{ opacity: 0; animation: steam 2.4s ease-out infinite; }}
  .say-cursor {{ fill: {ACCENT}; }}
  @keyframes spin {{
    0%, {pct(T1)}, {pct(T1 + TURN)}, {pct(T2)}, 100% {{ transform: scaleX(1); }}
    {pct(m1)}, {pct(m2)} {{ transform: scaleX(.03); }}
  }}
  @keyframes show-side {{
    0%, {pct(m1)} {{ opacity: 1; }} {pct(m1 + e)}, {pct(m2)} {{ opacity: 0; }} {pct(m2 + e)}, 100% {{ opacity: 1; }}
  }}
  @keyframes show-front {{
    0%, {pct(m1)} {{ opacity: 0; }} {pct(m1 + e)}, {pct(m2)} {{ opacity: 1; }} {pct(m2 + e)}, 100% {{ opacity: 0; }}
  }}
  @keyframes bubble {{
    0%, {pct(T1 + TURN)} {{ opacity: 0; transform: scale(.4); }}
    {pct(T1 + TURN + 0.25)}, {pct(T2 - 0.1)} {{ opacity: 1; transform: none; }}
    {pct(T2 + 0.05)}, 100% {{ opacity: 0; transform: scale(.4); }}
  }}
  @keyframes tap {{ from {{ transform: rotate(-2.5deg); }} to {{ transform: rotate(2.5deg); }} }}
  @keyframes nod {{ from {{ transform: rotate(-2deg); }} to {{ transform: rotate(2deg); }} }}
  @keyframes dangle {{ from {{ transform: rotate(-8deg); }} to {{ transform: rotate(10deg); }} }}
  @keyframes kick {{ from {{ transform: rotate(-7deg); }} to {{ transform: rotate(7deg); }} }}
  @keyframes hi {{ from {{ transform: rotate(10deg); }} to {{ transform: rotate(-18deg); }} }}
  @keyframes boing {{ from {{ transform: rotate(-7deg); }} to {{ transform: rotate(7deg); }} }}
  @keyframes talk {{ from {{ transform: scaleY(1); }} to {{ transform: scaleY(2.4); }} }}
  @keyframes pulse {{ 50% {{ opacity: .35; }} }}
  @keyframes blink-eye {{ 0%, 92%, 100% {{ transform: scaleY(1); }} 96% {{ transform: scaleY(.1); }} }}
  @keyframes steam {{ 0% {{ opacity: 0; transform: translateY(4px); }} 40% {{ opacity: .8; }}
                      100% {{ opacity: 0; transform: translateY(-12px); }} }}"""


# --- Składanie SVG ------------------------------------------------------------

def build():
    h = height_field()

    levels = np.arange(0.10, h.max(), 0.065)
    contour_svg = []
    for k, lv in enumerate(levels):
        major = k % 5 == 4  # co piąta poziomica = warstwica zasadnicza
        paths = [to_path(p) for p in contours(h, lv) if len(p) > 3]
        cls = "lv major" if major else "lv"
        body = "".join(
            f'<path d="{d}" pathLength="1" style="animation-delay:{0.15 + k * 0.08:.2f}s"/>'
            for d in paths
        )
        contour_svg.append(
            f'<g class="{cls}" style="animation-delay:{2.6 + k * 0.22:.2f}s">{body}</g>'
        )

    x0, fs = 64, 20
    subtitles = typed_lines(SUBTITLES, x0, 210, fs, 5.5, "1.2s", "sub", "blink sub-cursor")
    sx, sy, ss = SCENE_POS

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">
<title id="t">Hi, I'm Kajetan</title>
<desc id="d">Animated topographic map with a little robot typing at a computer, turning around now and then to say something, plus typed subtitles.</desc>
<style>
  .lv path {{ fill: none; stroke: {CONTOUR}; stroke-width: 1.1; stroke-opacity: .38;
             stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 2.2s ease-out forwards; }}
  .lv.major path {{ stroke: {ACCENT}; stroke-width: 1.8; stroke-opacity: .7; }}
  .lv {{ animation: elev 7s ease-in-out infinite; }}
  .title {{ font: 700 58px {SANS}; fill: {TEXT}; }}
  .hello {{ font: 16px {MONO}; fill: {MUTED}; }}
  .sub {{ font: {fs}px {MONO}; fill: {ACCENT}; }}
  .sub-cursor {{ fill: {ACCENT}; }}
  .say {{ font: 600 14px {MONO}; fill: {TEXT}; }}
  .small {{ font: 10px {MONO}; fill: {MUTED}; }}
  .rise {{ animation: rise .9s cubic-bezier(.2,.7,.2,1) both; }}
  .late {{ opacity: 0; animation: fade .8s 2.2s forwards; }}
  .blink {{ animation: blink 1s steps(1) infinite; }}
  @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
  @keyframes elev {{ 0%, 30%, 100% {{ opacity: .7; }} 15% {{ opacity: 1; }} }}
  @keyframes fade {{ to {{ opacity: 1; }} }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(14px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes blink {{ 50% {{ opacity: 0; }} }}
  {scene_css()}
  @media (prefers-reduced-motion: reduce) {{
    *, .lv path {{ animation: none !important; }}
    .lv path {{ stroke-dashoffset: 0; }}
    .code {{ transform: none; }}
  }}
</style>
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{BG0}"/><stop offset="1" stop-color="{BG1}"/>
  </linearGradient>
  <linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{BG0}" stop-opacity=".9"/>
    <stop offset=".38" stop-color="{BG0}" stop-opacity=".72"/>
    <stop offset=".6" stop-color="{BG0}" stop-opacity="0"/>
  </linearGradient>
  <filter id="glow" x="-100%" y="-100%" width="300%" height="300%">
    <feGaussianBlur stdDeviation="2.5" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <clipPath id="frame"><rect width="{W}" height="{H}" rx="18"/></clipPath>
</defs>

<g clip-path="url(#frame)">
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  {"".join(contour_svg)}
  <rect width="{W}" height="{H}" fill="url(#fade)"/>

  <!-- ramka mapy z naprzemiennymi odcinkami -->
  <rect x="12" y="12" width="{W - 24}" height="{H - 24}" fill="none" stroke="{MUTED}" stroke-opacity=".5"/>
  <rect x="16" y="16" width="{W - 32}" height="{H - 32}" fill="none" stroke="{ACCENT}" stroke-opacity=".35" stroke-width="3" stroke-dasharray="40 40"/>

  <!-- scena: biurko + robot; (0,0) sceny = siedzisko stołka -->
  <g transform="translate({sx},{sy}) scale({ss})">
    {desk()}
    <g class="spin">
      {robot_side()}
      {robot_front()}
    </g>
  </g>
  {bubble()}

  <!-- tekst -->
  <g class="rise"><text x="{x0}" y="98" class="hello">&gt; that's me!</text></g>
  <g class="rise" style="animation-delay:.15s"><text x="{x0 - 3}" y="160" class="title">Hi, I'm Kajetan</text></g>
  {subtitles}

  <!-- podziałka -->
  <g class="late">
    <rect x="{x0}" y="286" width="50" height="5" fill="{MUTED}"/>
    <rect x="{x0 + 50}" y="286" width="50" height="5" fill="none" stroke="{MUTED}"/>
    <text x="{x0}" y="306" class="small">0</text>
    <text x="{x0 + 46}" y="306" class="small">1</text>
    <text x="{x0 + 96}" y="306" class="small">2 km</text>
  </g>
</g>
</svg>
"""


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "assets" / "banner.svg"
    out.parent.mkdir(exist_ok=True)
    svg = build()
    out.write_text(svg, encoding="utf-8")
    print(f"Zapisano {out} ({len(svg) / 1024:.1f} KB)")
