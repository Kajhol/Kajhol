"""Generator animowanego banera do README profilu (assets/banner.svg).

Baner to mapa topograficzna: poziomice liczone algorytmem marching squares
z syntetycznego pola wysokości, robot schodzący ze szczytu, który macha
do oglądającego, i pisany tekst.
GitHub nie wykonuje JavaScriptu w README, więc cała animacja to CSS + SMIL
wewnątrz pliku SVG.

Uruchomienie (z katalogu repo):  python scripts/generate_banner.py
"""

from pathlib import Path
from xml.sax.saxutils import escape  # „&” w tekście musi trafić do SVG jako „&amp;”

import numpy as np

W, H = 1200, 340
STEP = 5  # rozdzielczość siatki w pikselach

# Paleta wzięta ze zdjęcia profilowego: granat koszulki, biel i błękit nadruku,
# ciepły ceglasty pomarańcz tła.
BG0, BG1 = "#080f24", "#15214a"
CONTOUR = "#7f9cd6"
ACCENT = "#a9c8ff"
WARM = "#ef8a5a"
TEXT = "#f5f7fb"
MUTED = "#7d8fb8"
SHELL, LIMB, VISOR = "#1f3263", "#18284f", "#060c1d"

MONO = "Consolas, 'DejaVu Sans Mono', Menlo, 'Courier New', monospace"
SANS = "'Segoe UI', 'Helvetica Neue', Ubuntu, Arial, sans-serif"

SUBTITLES = [
    "Software Engineer & AI Automation Enthusiast",
    "CS student @ Silesian University of Technology",
    "Building AI tools that optimize workflows",
]

# Robot: rysowany ze stopami w punkcie (0, 0). Startuje mały na szczycie góry
# („daleko”), schodzi i kończy duży, na prawie całą wysokość banera.
ROBOT_START_SCALE = 0.28
ROBOT_POS = (1000, 320, 1.35)  # x stóp, y stóp, skala — pozycja końcowa
WALK_BEGIN, WALK_TIME = 1.0, 3.0
ARRIVE = WALK_BEGIN + WALK_TIME  # wtedy staje, podnosi rękę i zaczyna mówić

# Teksty w dymku — pisane po kolei, w nieskończonej pętli
ROBOT_LINES = [
    "hello, human!",
    "01101000 01101001",  # „hi” w ASCII, binarnie
    "beep boop. welcome!",
    "while (alive) learn();",
    "scanning terrain...",
    'git commit -m "hi"',
    "check out my repos ↓",
]
SAY_SLOT = 3.2  # sekundy na jeden tekst


# --- Pole wysokości -----------------------------------------------------------

def height_field():
    """Suma „górek” Gaussa + łagodny szum, żeby poziomice nie były idealnymi elipsami."""
    xs = np.arange(0, W + 1, STEP, dtype=float)
    ys = np.arange(0, H + 1, STEP, dtype=float)
    x, y = np.meshgrid(xs, ys)

    def hill(cx, cy, sx, sy, amp):
        return amp * np.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))

    h = (
        hill(905, 165, 165, 115, 1.00)   # główny szczyt — meta trasy
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
    n = len(pts)
    rng = range(n - 1) if closed else range(n - 1)
    for k in rng:
        (x0, y0), (x1, y1) = pts[k], pts[k + 1]
        out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1),
                (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
    if closed:
        out.append(out[0])
    else:
        out.append(pts[-1])
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
    if closed:
        pts = chaikin(chaikin(pts[:-1] + [pts[0]], True), True)
    elif len(pts) > 2:
        pts = chaikin(chaikin(pts, False), False)
    pts = rdp(pts, 0.35)
    d = "M" + " L".join(f"{fmt(x)},{fmt(y)}" for x, y in pts)
    return d + ("Z" if closed else "")


# --- Pisany tekst (SMIL, krok co znak) ----------------------------------------

def typing_timelines(texts, x0, char_w, slot, dt_type=0.05, dt_erase=0.016):
    """Każdy tekst dostaje swój przedział `slot` sekund: pisze się, stoi, kasuje.

    Zwraca (czas cyklu, [klatki szerokości maski dla każdego tekstu], klatki pozycji kursora).
    """
    total = round(slot * len(texts), 3)
    lines, cursor = [], [(0.0, x0)]
    for n_line, text in enumerate(texts):
        n = len(text)
        s = n_line * slot
        erase_start = s + slot - n * dt_erase - 0.2
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


# --- Robot --------------------------------------------------------------------

def typed_lines(texts, x0, y, font_size, slot, begin, prefix, cursor_cls):
    """Pisane linie tekstu w jednym miejscu: maska (clipPath) odsłania tekst znak po znaku,
    kursor jedzie za ostatnim znakiem. Czcionka monospace, więc znak = 0.6 em."""
    char_w = font_size * 0.6
    total, frames_per_line, cursor_frames = typing_timelines(texts, x0, char_w, slot)
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


def robot():
    """Robot narysowany ze stopami w (0, 0). Kolejność rysowania = kolejność warstw.
    Atrybut transform ustawia go w pozycji końcowej; animacja CSS `approach` nadpisuje
    go na czas schodzenia ze szczytu."""
    rx, ry, rs = ROBOT_POS
    limb = f'fill="{LIMB}" stroke="{ACCENT}" stroke-width="2"'
    shell = f'fill="{SHELL}" stroke="{ACCENT}" stroke-width="2.5"'
    bars = "".join(
        f'<rect class="bar" x="{x}" y="-92" width="6" height="18" rx="2" fill="{c}" '
        f'style="animation-duration:{d}s;animation-delay:-{d / 2:.2f}s"/>'
        for x, c, d in [(-17, WARM, .7), (-7, ACCENT, .9), (3, WARM, .6), (13, ACCENT, 1.1)]
    )

    # Dymek po lewej stronie głowy, szeroki na najdłuższy tekst; ogonek celuje w głowę
    say_fs, pad = 14, 16
    bx1, by0, by1 = 912, 50, 90
    bx0 = bx1 - 2 * pad - max(len(t) for t in ROBOT_LINES) * say_fs * 0.6 - 10
    tip = (rx - 50 * rs - 4, ry - 158 * rs)
    bubble = (f"M{bx0 + 14:.0f},{by0} H{bx1 - 14} Q{bx1},{by0} {bx1},{by0 + 14} V{by1 - 14} "
              f"Q{bx1},{by1} {bx1 - 14},{by1} H{bx1 - 18} L{tip[0]:.0f},{tip[1]:.0f} "
              f"L{bx1 - 42},{by1} H{bx0 + 14:.0f} Q{bx0:.0f},{by1} {bx0:.0f},{by1 - 14} V{by0 + 14} "
              f"Q{bx0:.0f},{by0} {bx0 + 14:.0f},{by0}Z")
    said = typed_lines(ROBOT_LINES, round(bx0 + pad), by0 + 25, say_fs, SAY_SLOT,
                       f"{ARRIVE + 0.6}s", "say", "blink say-cursor")

    return f"""
  <g class="approach" transform="translate({rx},{ry}) scale({rs})">
    <ellipse cx="0" cy="2" rx="58" ry="9" fill="#000" opacity=".4"/>
    <g class="idle">
    <g class="bob">
      <g class="legL"><rect x="-30" y="-44" width="20" height="40" rx="7" {limb}/><rect x="-37" y="-10" width="30" height="12" rx="6" {limb}/></g>
      <g class="legR"><rect x="10" y="-44" width="20" height="40" rx="7" {limb}/><rect x="7" y="-10" width="30" height="12" rx="6" {limb}/></g>
      <g class="armL"><rect x="-64" y="-110" width="16" height="54" rx="8" {limb}/><circle cx="-56" cy="-52" r="10" {limb}/></g>
      <g class="raise"><g class="wave"><rect x="48" y="-110" width="16" height="54" rx="8" {limb}/><circle cx="56" cy="-52" r="10" {limb}/></g></g>
      <rect x="-46" y="-118" width="92" height="80" rx="20" {shell}/>
      <rect x="-26" y="-102" width="52" height="34" rx="8" fill="{VISOR}"/>
      {bars}
      <rect x="-9" y="-130" width="18" height="14" rx="4" {limb}/>
      <line x1="0" y1="-190" x2="0" y2="-206" stroke="{ACCENT}" stroke-width="3"/>
      <circle class="ant" cx="0" cy="-211" r="7" fill="{WARM}" filter="url(#glow)"/>
      <rect x="-60" y="-170" width="14" height="28" rx="5" {limb}/>
      <rect x="46" y="-170" width="14" height="28" rx="5" {limb}/>
      <rect x="-50" y="-192" width="100" height="66" rx="22" {shell}/>
      <rect x="-38" y="-180" width="76" height="42" rx="14" fill="{VISOR}"/>
      <rect class="eye" x="-25" y="-170" width="14" height="18" rx="6" fill="{ACCENT}" filter="url(#glow)"/>
      <rect class="eye" x="11" y="-170" width="14" height="18" rx="6" fill="{ACCENT}" filter="url(#glow)"/>
      <path d="M-11,-149 Q0,-141 11,-149" fill="none" stroke="{WARM}" stroke-width="3" stroke-linecap="round"/>
    </g>
    </g>
  </g>
  <g class="bubble" style="transform-origin:{tip[0]:.0f}px {tip[1]:.0f}px">
    <path d="{bubble}" fill="{BG0}" fill-opacity=".85" stroke="{ACCENT}" stroke-width="1.5"/>
    {said}
  </g>"""


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

    # Robot startuje ze szczytu głównej góry
    sub = h[:, 160:200]  # x ∈ [800, 1000)
    jy, ix = np.unravel_index(np.argmax(sub), sub.shape)
    sx, sy = (ix + 160) * STEP, jy * STEP + 8
    rx, ry, rs = ROBOT_POS
    steps = round(WALK_TIME / 0.6)  # jeden krok = 0.6 s

    x0, fs = 64, 20
    subtitles = typed_lines(SUBTITLES, x0, 210, fs, 5.5, "1.2s", "sub", "blink sub-cursor")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">
<title id="t">Hi, I'm Kajetan</title>
<desc id="d">Animated topographic map with a robot that walks down from the summit, waves and keeps talking, plus typed subtitles.</desc>
<style>
  .lv path {{ fill: none; stroke: {CONTOUR}; stroke-width: 1.1; stroke-opacity: .38;
             stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 2.2s ease-out forwards; }}
  .lv.major path {{ stroke: {ACCENT}; stroke-width: 1.8; stroke-opacity: .7; }}
  .lv {{ animation: elev 7s ease-in-out infinite; }}
  .title {{ font: 700 58px {SANS}; fill: {TEXT}; }}
  .hello {{ font: 16px {MONO}; fill: {MUTED}; }}
  .sub {{ font: {fs}px {MONO}; fill: {ACCENT}; }}
  .say {{ font: 600 14px {MONO}; fill: {TEXT}; }}
  .small {{ font: 10px {MONO}; fill: {MUTED}; }}

  .sub-cursor, .say-cursor {{ fill: {ACCENT}; }}

  /* robot: transform-origin podany we współrzędnych robota (stopy = 0,0) */
  .approach, .idle, .bob, .legL, .legR, .armL, .raise, .wave, .bubble {{ transform-box: view-box; }}
  .approach {{ animation: approach {WALK_TIME}s ease-in-out {WALK_BEGIN}s both; }}
  .bob {{ animation: bob .6s linear {WALK_BEGIN}s {steps}; }}
  .legL {{ animation: legL .6s linear {WALK_BEGIN}s {steps}; }}
  .legR {{ animation: legR .6s linear {WALK_BEGIN}s {steps}; }}
  .armL {{ transform-origin: -56px -104px; animation: swing .6s ease-in-out {WALK_BEGIN}s {steps}; }}
  .idle {{ animation: hover 3.2s ease-in-out {ARRIVE}s infinite; }}
  .raise {{ transform-origin: 56px -104px;
           animation: swing .6s ease-in-out {WALK_BEGIN}s {steps} reverse, raise .5s ease-out {ARRIVE}s forwards; }}
  .wave {{ transform-origin: 56px -104px; animation: wave 3s ease-in-out {ARRIVE + 0.5}s infinite; }}
  .eye {{ transform-box: fill-box; transform-origin: center; animation: blink-eye 4s infinite; }}
  .ant {{ animation: pulse 1.6s ease-in-out infinite; }}
  .bar {{ transform-box: fill-box; transform-origin: bottom; animation: eq ease-in-out infinite alternate; }}
  .bubble {{ opacity: 0; animation: pop .45s cubic-bezier(.3,1.6,.5,1) {ARRIVE + 0.3}s forwards; }}
  @keyframes approach {{
    0% {{ opacity: 0; transform: translate({sx}px, {sy}px) scale({ROBOT_START_SCALE}); }}
    12% {{ opacity: 1; }}
    100% {{ opacity: 1; transform: translate({rx}px, {ry}px) scale({rs}); }}
  }}
  @keyframes bob {{ 25%, 75% {{ transform: translateY(-7px); }} }}
  @keyframes legL {{ 25% {{ transform: translateY(-9px); }} 50% {{ transform: none; }} }}
  @keyframes legR {{ 50% {{ transform: none; }} 75% {{ transform: translateY(-9px); }} }}
  @keyframes swing {{ 25% {{ transform: rotate(14deg); }} 75% {{ transform: rotate(-14deg); }} }}
  @keyframes hover {{ 50% {{ transform: translateY(-4px); }} }}
  @keyframes raise {{ to {{ transform: rotate(-130deg); }} }}
  @keyframes wave {{
    0%, 60%, 100% {{ transform: rotate(0); }}
    10%, 30%, 50% {{ transform: rotate(22deg); }}
    20%, 40% {{ transform: rotate(-12deg); }}
  }}
  @keyframes blink-eye {{ 0%, 92%, 100% {{ transform: scaleY(1); }} 96% {{ transform: scaleY(.1); }} }}
  @keyframes pulse {{ 50% {{ opacity: .35; }} }}
  @keyframes eq {{ from {{ transform: scaleY(.25); }} to {{ transform: scaleY(1); }} }}
  @keyframes pop {{ from {{ opacity: 0; transform: scale(.3); }} to {{ opacity: 1; transform: none; }} }}
  .rise {{ animation: rise .9s cubic-bezier(.2,.7,.2,1) both; }}
  .late {{ opacity: 0; animation: fade .8s 2.2s forwards; }}
  .blink {{ animation: blink 1s steps(1) infinite; }}
  .needle {{ transform-origin: 1140px 285px; animation: wobble 5s ease-in-out infinite alternate; }}
  @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
  @keyframes elev {{ 0%, 30%, 100% {{ opacity: .7; }} 15% {{ opacity: 1; }} }}
  @keyframes fade {{ to {{ opacity: 1; }} }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(14px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes blink {{ 50% {{ opacity: 0; }} }}
  @keyframes wobble {{ from {{ transform: rotate(-9deg); }} to {{ transform: rotate(7deg); }} }}
  @media (prefers-reduced-motion: reduce) {{
    .lv path {{ animation: none; stroke-dashoffset: 0; }}
    .lv, .needle, .blink, .bubble, .rise {{ animation: none; opacity: 1; }}
    .approach, .idle, .bob, .legL, .legR, .armL, .wave, .eye, .ant, .bar {{ animation: none; }}
    .raise {{ animation: none; transform: rotate(-130deg); }}
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
    <feGaussianBlur stdDeviation="3" result="b"/>
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

  <!-- robot -->
  {robot()}

  <!-- tekst -->
  <g class="rise"><text x="{x0}" y="98" class="hello">&gt; that's me!</text></g>
  <g class="rise" style="animation-delay:.15s"><text x="{x0 - 3}" y="160" class="title">Hi, I'm Kajetan</text></g>
  {subtitles}

  <!-- podziałka i róża wiatrów -->
  <g class="late">
    <rect x="{x0}" y="286" width="50" height="5" fill="{MUTED}"/>
    <rect x="{x0 + 50}" y="286" width="50" height="5" fill="none" stroke="{MUTED}"/>
    <text x="{x0}" y="306" class="small">0</text>
    <text x="{x0 + 46}" y="306" class="small">1</text>
    <text x="{x0 + 96}" y="306" class="small">2 km</text>
  </g>
  <g class="late">
    <circle cx="1140" cy="285" r="20" fill="{BG0}" fill-opacity=".6" stroke="{MUTED}"/>
    <g class="needle">
      <path d="M1140,268 L1145,285 L1140,282 L1135,285Z" fill="{WARM}"/>
      <path d="M1140,302 L1145,285 L1140,288 L1135,285Z" fill="{MUTED}"/>
    </g>
    <text x="1136" y="259" class="small" style="fill:{TEXT}">N</text>
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
