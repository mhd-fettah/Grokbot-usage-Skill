#!/usr/bin/env python3
"""Render the weekly Grok Bot usage report as a PNG card. See README/skill for the JSON schema."""
import argparse, json, os, sys
from datetime import datetime, timedelta
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

VERSION = "v22"
HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "fonts", "Inter-VariableFont_opsz,wght.ttf")
WEEK_H = 168.0
THEMES = {
    "dark": dict(
        BG=(14, 15, 18), CARD=(22, 24, 29), LINE=(38, 41, 49), TRACK=(40, 43, 52),
        TEXT=(242, 243, 245), MUTED=(138, 143, 152), FAINT=(98, 103, 112), ACCENT=(124, 156, 255),
        SLICES=[(124, 156, 255), (167, 139, 250), (56, 189, 248), (99, 102, 241), (199, 210, 254)],
        OTHER=(78, 83, 96), BAR_TRACK=(44, 47, 56),
        VERDICT_COLORS={"SPARE": (52, 199, 123), "CLOSE": (251, 146, 60), "SHORT": (242, 85, 90), "TOO EARLY": (138, 143, 152)}),
    "light": dict(
        BG=(240, 241, 244), CARD=(255, 255, 255), LINE=(229, 231, 235), TRACK=(234, 236, 241),
        TEXT=(17, 19, 24), MUTED=(107, 114, 128), FAINT=(150, 156, 168), ACCENT=(79, 110, 247),
        SLICES=[(79, 110, 247), (139, 108, 245), (14, 165, 233), (55, 48, 163), (165, 180, 252)],
        OTHER=(203, 207, 214), BAR_TRACK=(218, 221, 227),
        VERDICT_COLORS={"SPARE": (22, 163, 74), "CLOSE": (234, 88, 12), "SHORT": (220, 38, 38), "TOO EARLY": (107, 114, 128)}),
}


def apply_theme(name):
    name = (name or "light").lower()
    if name not in THEMES:
        raise SystemExit(f"unknown theme {name!r}; use light or dark")
    globals().update(THEMES[name])
    return name


apply_theme("light")
W, OUT_SCALE, SS = 540, 2, 2  # logical width; output 1080 px; supersampling
K = OUT_SCALE * SS
PAD, PAD_X, PAD_B, IN = 19.5, 19.5, 38.5, 30  # margins top/sides/bottom (x2 px), inner padding
_warned = False


def fmt_dh(hours, mode="floor"):
    h = max(int(hours) if mode == "floor" else int(round(hours)), 0)
    if h == 0:
        return "<1h"
    d, r = divmod(h, 24)
    return f"{d}d {r}h" if d else f"{r}h"


def compute(d):
    used, left = float(d["used_pct"]), float(d["hours_left"])
    E = WEEK_H - left
    r = {"used": used, "left": left, "elapsed": E, "left_dh": fmt_dh(left),
         "ideal": max(0.0, min(100.0, E / WEEK_H * 100))}
    if E < 6 or used <= 0:
        r.update(verdict="TOO EARLY", rate=None, projected=None, short_h=None,
                 detail="Not enough data yet", pace=[("Too early to project a pace", None)])
        return r
    R = used / E
    to100 = (100 - used) / R if used < 100 else 0.0
    P = used + R * left
    r.update(rate=R, projected=P, hours_to_100=to100, short_h=None)
    if used >= 100:  # limit already reached: estimate when from the average pace
        ro_h, known = E * 100 / used, False
        if d.get("ranout_iso") and d.get("reset_iso"):  # optional: the real moment it hit 100%
            try:
                gone = (datetime.fromisoformat(d["reset_iso"]) - datetime.fromisoformat(d["ranout_iso"])).total_seconds() / 3600
                ro_h, known = min(max(WEEK_H - gone, 0.0), E), True
            except ValueError:
                pass
        r.update(verdict="SHORT", out=True, ro_known=known, short_h=left, detail="Limit reached", runout_h=ro_h,
                 pace=[("Limit reached", None)])
    elif to100 < left - 2:
        dh = fmt_dh(left - to100, "round")
        r.update(verdict="SHORT", short_h=left - to100, detail=f"Short by {dh}", runout_h=E + to100,
                 pace=[("At this rate you'll run out ", None), (f"~{dh}", "v"), (" before reset", None)])
    else:
        r.update(pace=[("At this rate you'll reach ", None), (f"~{min(P, 100):.0f}%", "v"), (" by reset", None)])
        if P < 90:
            r.update(verdict="SPARE", detail=f"~{100 - P:.0f}% will go unused")
        else:
            r.update(verdict="CLOSE", detail=f"~{min(P, 100):.0f}% by reset")
    return r


def fmt_pct(x):
    return f"{x:.1f}%" if abs(x - round(x)) > 0.05 else f"{x:.0f}%"


def load_font(px):
    global _warned
    if os.path.exists(FONT):
        return ImageFont.truetype(FONT, px)
    if not _warned:
        print(f"warning: font not found at {FONT}; using Pillow's default font", file=sys.stderr)
        _warned = True
    try:
        return ImageFont.load_default(px)
    except TypeError:
        return ImageFont.load_default()


class Painter:
    def __init__(self, h):
        self.img = Image.new("RGB", (int(round(W * K)), int(round(h * K))), BG)
        self.d = ImageDraw.Draw(self.img)
        self._fonts = {}

    def font(self, size, weight=400):
        key = (size, weight)
        if key not in self._fonts:
            f = load_font(int(round(size * K)))
            try:
                f.set_variation_by_axes([min(32, max(14, size)), weight])
            except Exception:
                pass
            self._fonts[key] = f
        return self._fonts[key]

    def text(self, xy, s, size, weight=400, fill=None, anchor="la"):
        self.d.text((xy[0] * K, xy[1] * K), s, font=self.font(size, weight),
                    fill=TEXT if fill is None else fill, anchor=anchor)

    def tw(self, s, size, weight=400):
        return self.d.textlength(s, font=self.font(size, weight)) / K

    def rrect(self, box, r, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = box
        self.d.rounded_rectangle((x0 * K, y0 * K, x1 * K, y1 * K), radius=r * K, fill=fill,
                                 outline=outline, width=int(width * K))

    def line(self, x0, y0, x1, y1, fill=None, width=1):
        self.d.line((x0 * K, y0 * K, x1 * K, y1 * K), fill=LINE if fill is None else fill,
                    width=max(1, int(width * K)))

    def ellipsize(self, s, size, weight, maxw):
        if self.tw(s, size, weight) <= maxw:
            return s
        while s and self.tw(s + "…", size, weight) > maxw:
            s = s[:-1]
        return s.rstrip(" ·,") + "…"


def mix(c, bg, a):
    return tuple(int(c[i] * a + bg[i] * (1 - a)) for i in range(3))


def lum(c):
    f = lambda v: (v / 255) / 12.92 if v <= 10 else ((v / 255 + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])




def stripes(size, step, sw):
    pat = Image.new("L", size, 0)
    pd = ImageDraw.Draw(pat)
    for sx in range(-size[1], size[0] + step, step):
        pd.line((sx, size[1], sx + size[1], 0), fill=255, width=sw)
    return pat


def col_w(p, rows):
    return max(p.tw(t, *f) for t, f, _ in rows)


def place_cols(p, caps, bx0, bx1):
    """caps: dicts with x, rows [(text, font, colour)]. Centre on x; if neighbours touch, push them apart
    (left one ends at its line, right one starts at its line); if still touching, drop to a lower tier."""
    for c in caps:
        c["w"] = col_w(p, c["rows"])
        c["al"] = c.get("al", "c")
        c["tier"] = 0
    def ext(c):
        if c["al"] == "r":
            l = c["x"] + c.get("pad", 0) - c["w"]
        elif c["al"] == "l":
            l = c["x"] - c.get("pad", 0)
        else:
            l = c["x"] - c["w"] / 2
        l = min(max(l, bx0), bx1 - c["w"])
        c["l"] = l
        return l, l + c["w"]
    caps.sort(key=lambda c: c["x"])
    for c in caps:
        ext(c)
    for a, b in zip(caps, caps[1:]):
        if a["l"] + a["w"] + 12 > b["l"]:
            if a["al"] == "c":
                a["al"], a["pad"] = "r", 4
            if b["al"] == "c":
                b["al"], b["pad"] = "l", 4
            ext(a); ext(b)
            if a["l"] + a["w"] + 12 > b["l"]:
                b["tier"] = a["tier"] + 1
    return max(c["tier"] for c in caps) + 1 if caps else 1


def draw_cols(p, caps, y0, below, tier_h):
    for c in caps:
        rows = c["rows"] if below else c["rows"]
        n = len(rows)
        for i, (t, f, colr) in enumerate(rows):
            if below:
                yb = y0 + tier_h * c["tier"] + 16 + 15 * i
            else:
                yb = y0 - tier_h * c["tier"] - 7 - 15 * (n - 1 - i)
            if c["al"] == "r":
                p.text((c["l"] + c["w"], yb), t, *f, colr, anchor="rs")
            elif c["al"] == "l":
                p.text((c["l"], yb), t, *f, colr, anchor="ls")
            else:
                p.text((c["l"] + c["w"] / 2, yb), t, *f, colr, anchor="ms")


def stacked(p, d, m, vc, layout, header_end, x0, x1, bx0, bx1, card1_bottom):
    NAME, VAL, SUB = (10.5, 500), (12, 650), (10.5, 500)
    bw_ = bx1 - bx0
    X = lambda pct: bx0 + bw_ * min(max(pct, 0), 100) / 100
    track = BAR_TRACK if layout == "split" else TRACK
    sep = BG if layout == "split" else CARD
    solid = ACCENT if m["verdict"] == "TOO EARLY" else vc
    dark_bg = lum(BG) <= 0.5
    now_col = TEXT
    reset = None
    if d.get("reset_iso"):
        try:
            reset = datetime.fromisoformat(d["reset_iso"])
        except ValueError:
            reset = None
    def clock(h_from_start):
        t = reset - timedelta(hours=WEEK_H - h_from_start)
        t = (t + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
        return t.strftime("%a ") + t.strftime("%I %p").lstrip("0")
    keep = lambda x: min(max(x, bx0 + 2.5), bx1 - 2.5)  # lines kept off the rounded corners
    now = m["elapsed"] / WEEK_H * 100
    nx, ux = X(now), X(m["used"])
    nxl, uxl = keep(nx), keep(ux)
    # captions above: usage
    above = [dict(x=uxl, rows=[("Used", NAME, MUTED), (fmt_pct(m["used"]), VAL, TEXT)])]
    t_above = place_cols(p, above, bx0, bx1)
    # captions below: time
    now_rows = [("Now", NAME, MUTED), (clock(m["elapsed"]) if reset else f"{m['left_dh']} left", VAL, TEXT),
                (f"Even pace {fmt_pct(round(m['ideal']))}", SUB, MUTED)]
    below = [dict(x=nxl, rows=now_rows)]
    rx = zx = None
    if m.get("runout_h") is not None:
        ro = m["runout_h"] / WEEK_H * 100
        rx = keep(X(ro))
        when = clock(m["runout_h"]) if reset else "in ~" + fmt_dh(m["runout_h"] - m["elapsed"], "round")
        if m.get("out"):  # already happened: estimated from the average pace
            if abs(rx - nxl) < 6:  # ran out just now: one line, the Now caption says it
                below[0]["rows"][0] = ("Now · ran out", NAME, vc)
                rx = None
            else:
                ago = "~" + fmt_dh(m["elapsed"] - m["runout_h"], "round") + " ago"
                tilde = "" if m.get("ro_known") else "~"
                below.append(dict(x=rx, rows=[("Ran out", NAME, vc), ((tilde + when) if reset else ago, VAL, vc)]))
        else:
            below.append(dict(x=rx, rows=[("Will run out", NAME, vc), (when, VAL, vc)]))
        zx = X(max(ro, now))
        if m.get("out") and rx is not None:  # out period already under way: hatch starts at the run-out
            zx = X(ro)
    elif m["projected"] is not None:
        P = min(m["projected"], 100)
        rows = [("At reset", NAME, MUTED), (f"~{P:.0f}%", VAL, vc)]
        if m["verdict"] == "SPARE":
            rows.append((f"Spare ~{100 - P:.0f}%", SUB, MUTED))
        below.append(dict(x=bx1, al="r", rows=rows))
    t_below = place_cols(p, below, bx0, bx1)
    # geometry
    uh, wh, BR = 14, 28, 4.5
    room = 7 + 15 * 1 + 10 + 30 * (t_above - 1)
    if layout == "split":
        sy = card1_bottom + 10 + room
    elif layout == "lines":
        p.line(x0, header_end + 20, x1, header_end + 20)
        sy = header_end + 34 + room
    else:
        sy = header_end + 24 + room
    wy = sy + uh
    sb = wy + wh
    X0, Y0, X1, Y1 = [int(round(v * K)) for v in (bx0, sy, bx1, sb)]
    size, box = (X1 - X0 + 1, Y1 - Y0 + 1), (X0, Y0, X1 + 1, Y1 + 1)
    lx_ = lambda x: int(round(x * K)) - X0
    ly_ = lambda y: int(round(y * K)) - Y0
    layer = Image.new("RGB", size, track)
    ld = ImageDraw.Draw(layer)
    # usage bar
    uy1 = ly_(wy) - 1
    if m["verdict"] != "TOO EARLY":
        ld.rectangle((0, 0, size[0], uy1), fill=mix(vc, sep, 0.26))
    if ux > bx0:
        ld.rectangle((0, 0, lx_(ux) - 1, uy1), fill=solid)
    if m["verdict"] != "TOO EARLY" and abs(ux - nx) > 3:  # the gap between usage and pace
        if ux > nx:  # ahead of pace: the overspend in a deeper shade
            ld.rectangle((lx_(nx), 0, lx_(ux) - 1, uy1), fill=mix(vc, (0, 0, 0), 0.84) if not dark_bg else mix(vc, (0, 0, 0), 0.78))
        else:  # behind pace: unused headroom up to Now lightly striped
            z = Image.new("L", size, 0)
            ImageDraw.Draw(z).rectangle((lx_(ux), 0, lx_(nx) - 1, uy1), fill=255)
            layer.paste(mix(vc, sep, 0.5), (0, 0) + size,
                        ImageChops.multiply(z, stripes(size, int(6 * K), int(1.8 * K))))
    # week bar
    el_col = mix(MUTED, CARD, 0.6) if dark_bg else mix(MUTED, TEXT, 0.35)
    if nx > bx0:
        ld.rectangle((0, ly_(wy), lx_(nx) - 1, size[1]), fill=el_col)
    ztint = None
    if zx is not None:
        ztint = mix(vc, sep, 0.14)
        z = Image.new("L", size, 0)
        ImageDraw.Draw(z).rectangle((lx_(zx), ly_(wy), size[0], size[1]), fill=255)
        layer.paste(ztint, (0, 0) + size, z)
        layer.paste(mix(vc, sep, 0.6), (0, 0) + size, ImageChops.multiply(z, stripes(size, int(8 * K), int(2.6 * K))))
        if zx < nx:  # the part of the out period that has already passed: same stripes on the elapsed tone
            ptint = mix(vc, el_col, 0.22)
            zp = Image.new("L", size, 0)
            ImageDraw.Draw(zp).rectangle((lx_(zx), ly_(wy), lx_(nx) - 1, size[1]), fill=255)
            layer.paste(ptint, (0, 0) + size, zp)
            layer.paste(mix(vc, el_col, 0.75), (0, 0) + size, ImageChops.multiply(zp, stripes(size, int(8 * K), int(2.6 * K))))
    outer = Image.new("L", size, 0)
    ImageDraw.Draw(outer).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=BR * K, fill=255)
    p.img.paste(layer, box, outer)
    p.rrect((bx0, wy - 0.4, bx1, wy + 0.4), 0, fill=sep)  # hairline seam between the two bars
    for k in range(1, 7):  # day divisions, week bar only
        xt = bx0 + bw_ * 24 * k / WEEK_H
        p.rrect((xt - 0.75, wy, xt + 0.75, sb + 0.5), 0, fill=sep)
    LW, HALO = 1.25, 1.0
    vlines = [(nxl, wy, sb)] + ([(rx, wy, sb)] if rx is not None else [])
    if reset is not None:  # weekday names inside the week bar
        DF = (12, 650)
        f = p.font(*DF)
        on_el = (255, 255, 255) if 1.05 / (lum(el_col) + 0.05) >= 3.0 else (17, 19, 24)
        if zx is not None and zx < nx:
            regions = [(bx0, zx, on_el, None), (zx, nx, on_el, mix(vc, el_col, 0.22)), (nx, bx1, TEXT, ztint)]
        else:
            regions = [(bx0, nx, on_el, None), (nx, zx if zx is not None else bx1, MUTED, None)]
            if zx is not None:
                regions.append((zx, bx1, TEXT, ztint))
        mx = [nxl] + ([rx] if rx is not None else [])
        for k in range(7):
            mid = reset - timedelta(hours=WEEK_H - 24 * k - 12)
            xm = bx0 + bw_ * (24 * k + 12) / WEEK_H
            s0, s1 = xm - bw_ * 12 / WEEK_H + 2, xm + bw_ * 12 / WEEK_H - 2
            clr = LW + HALO + 2.5
            # free gaps inside the segment once the marker lines (plus clearance) are cut out
            cuts = sorted(x for x in mx if s0 < x < s1)
            edges = [s0] + [v for x in cuts for v in (x - clr, x + clr)] + [s1]
            gaps = [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2) if edges[i + 1] > edges[i]]
            txt = None
            for cand in (mid.strftime("%a"), mid.strftime("%a")[0]):  # full name, else its first letter
                nw = p.tw(cand, *DF)
                fits = [(a, b) for a, b in gaps if b - a >= nw]
                if fits:  # nearest spot to the segment centre that clears every line
                    xm = min((min(max(xm, a + nw / 2), b - nw / 2) for a, b in fits), key=lambda c: abs(c - xm))
                    txt = cand
                    break
            if txt is None:
                continue
            lw, lh = int(p.tw(txt, *DF) * K) + 8, int(wh * K)
            tm = Image.new("L", (lw, lh), 0)
            ImageDraw.Draw(tm).text((lw / 2, lh / 2), txt, font=f, fill=255, anchor="mm")
            ox, oy = int(round(xm * K - lw / 2)), int(round(wy * K))
            halo = tm.filter(ImageFilter.MaxFilter(2 * int(1.2 * K) + 1))
            for ra, rb, colr, hal in regions:
                a2, b2 = max(int(round(ra * K)) - ox, 0), min(int(round(rb * K)) - ox, lw)
                if b2 > a2 and hal is not None:
                    hp = Image.new("L", (lw, lh), 0)
                    hp.paste(halo.crop((a2, 0, b2, lh)), (a2, 0))
                    p.img.paste(hal, (ox, oy, ox + lw, oy + lh), hp)
                if b2 > a2:
                    part = Image.new("L", (lw, lh), 0)
                    part.paste(tm.crop((a2, 0, b2, lh)), (a2, 0))
                    p.img.paste(colr, (ox, oy, ox + lw, oy + lh), part)
    # marker lines: Used through the usage bar (stub up), Now through both (stubs both ways),
    # Will run out through the week bar (stub down)
    def mline(x, ya, yb, colr, up, down):
        p.rrect((x - LW - HALO, ya, x + LW + HALO, yb), 0, fill=sep)
        p.rrect((x - LW, ya - (4.5 if up else 0), x + LW, yb + (4.5 if down else 0)), LW if (up and down) else 0.6, fill=colr)
    if rx is not None:
        mline(rx, wy, sb, vc, False, True)
    if m["used"] > 0:
        mline(uxl, sy, wy, now_col, True, False)
    mline(nxl, sy, sb, now_col, True, True)
    draw_cols(p, above, sy, False, 30)
    draw_cols(p, below, sb, True, 46)
    return sb + 6 + max(46 * (t_below - 1) + 15 * (len(c["rows"]) - 1) + 16 for c in below) + 4


def render(d, p):
    m = compute(d)
    vc = VERDICT_COLORS[m["verdict"]]
    x0, x1 = PAD_X + IN, W - PAD_X - IN
    y = PAD + IN
    p.text((x0, y), "Usage report", 20, 650)
    p.text((x1, y + 4), "Weekly limit", 12, 450, MUTED, anchor="ra")
    y += 46
    big = fmt_pct(m["used"])
    p.text((x0, y), big, 60, 700, TEXT, anchor="lt")
    p.text((x0, y + 70), f"Resets in {m['left_dh']}", 15, 650, TEXT)
    p.text((x0, y + 92), d.get("reset_label", ""), 12, 450, MUTED)
    label = "Ran out" if m.get("out") else m["verdict"].capitalize()
    pw, ph = p.tw(label, 15, 650) + 36, 32
    px0 = x1 - pw
    ib = p.d.textbbox((x0 * K, y * K), big, font=p.font(60, 700), anchor="lt")
    py0 = (ib[1] + ib[3]) / 2 / K - ph / 2  # pill centered on the number's ink box
    p.rrect((px0, py0, x1, py0 + ph), ph / 2, fill=mix(vc, CARD, 0.16), outline=mix(vc, CARD, 0.45), width=1)
    cx, cy = px0 + 15, py0 + ph / 2
    p.d.ellipse(((cx - 4) * K, (cy - 4) * K, (cx + 4) * K, (cy + 4) * K), fill=vc)
    p.text((px0 + 26, cy), label, 15, 650, vc, anchor="lm")
    p.text((x1, y + 70), m["detail"], 15, 600, TEXT, anchor="ra")
    pace = f"{m['rate']:.2f}%/h  ·  {m['rate'] * 24:.1f}%/day" if m["rate"] is not None else "—"
    plabel = "Pace"
    if m.get("out") and d.get("reset_iso") and m["elapsed"] - m["runout_h"] >= 1:
        t = datetime.fromisoformat(d["reset_iso"]) - timedelta(hours=WEEK_H - m["runout_h"])
        t = (t + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
        pace = ("" if m.get("ro_known") else "~") + t.strftime("%a ") + t.strftime("%I %p").lstrip("0")
        plabel = "Out since"
    p.text((x1, y + 92), pace, 12, 550, MUTED, anchor="ra")
    p.text((x1 - p.tw(pace, 12, 550) - 8, y + 92), plabel, 12, 450, FAINT, anchor="ra")
    layout = d.get("_layout", "lines")
    header_end = y + 106
    if layout == "split":
        card1_bottom = header_end + IN - 4
        p.cards = [(PAD, card1_bottom)]
        ox0, ox1 = PAD_X + 2, W - PAD_X - 2
    else:
        p.cards = []
        ox0, ox1 = x0, x1
    labels_end = stacked(p, d, m, vc, layout, header_end, x0, x1, ox0, ox1,
                          card1_bottom if layout == "split" else None)
    if layout == "split":
        card2_top = labels_end + 14
        y = card2_top + IN - 4
    elif layout == "lines":
        card2_top = PAD
        p.line(x0, labels_end + 16, x1, labels_end + 16)
        y = labels_end + 38
    else:
        card2_top = PAD
        y = labels_end + 34
    p.text((x0, y), "Bots", 11, 500, MUTED)
    p.text((x1, y), "share of Grok Bot usage", 11, 450, FAINT, anchor="ra")
    y += 28
    bots = sorted(d.get("breakdown", []), key=lambda b: -float(b.get("pct", 0)))
    if bots:
        TINY = float(d.get("other_threshold_pct", 3))
        big_bots = [b for b in bots if float(b.get("pct", 0)) >= TINY][:len(SLICES)]
        colors, slices, other = {}, [], 0.0
        for b in bots:
            if b in big_bots:
                colors[id(b)] = SLICES[big_bots.index(b)]
                slices.append((float(b["pct"]), colors[id(b)]))
            else:
                colors[id(b)] = OTHER
                other += float(b.get("pct", 0))
        if other > 0:
            slices.append((other, OTHER))
        total = sum(v for v, _ in slices) or 1.0
        D, top0 = 150, y
        cxx, cyy, R = x0 + D / 2, y + D / 2, D / 2
        ang = -90.0
        gap = 1.6 if len([v for v, _ in slices if v > 0]) > 1 else 0
        for v, col in slices:
            sweep = 360.0 * v / total
            if sweep <= 0:
                continue
            g = min(gap, sweep / 3)
            p.d.pieslice(((cxx - R) * K, (cyy - R) * K, (cxx + R) * K, (cyy + R) * K),
                         ang + g / 2, ang + sweep - g / 2, fill=col)
            ang += sweep
        ri = R * 0.62
        p.d.ellipse(((cxx - ri) * K, (cyy - ri) * K, (cxx + ri) * K, (cyy + ri) * K), fill=CARD)
        p.text((cxx, cyy - 8), f"{len(bots)}", 22, 700, TEXT, anchor="mm")
        p.text((cxx, cyy + 13), "bots", 11, 450, MUTED, anchor="mm")
        cap_h = 0
        if other > 0:
            cap = f"Grey = Other (under {TINY:g}% each)"
            ctw = p.tw(cap, 10, 450)
            p.d.ellipse(((cxx - ctw / 2 - 10) * K, (y + D + 10.5) * K, (cxx - ctw / 2 - 3) * K, (y + D + 17.5) * K), fill=OTHER)
            p.text((cxx + 4, y + D + 14), cap, 10, 450, FAINT, anchor="mm")
            cap_h = 24
        lx, ly = x0 + D + 26, y
        branch = mix(MUTED, CARD, 0.55)
        for b in bots:
            ptxt = fmt_pct(float(b.get("pct", 0)))
            mid = ly + 9
            p.d.ellipse((lx * K, (mid - 5) * K, (lx + 10) * K, (mid + 5) * K), fill=colors[id(b)])
            pw_ = p.tw(ptxt, 14, 600)
            p.text((lx + 18, mid), p.ellipsize(str(b.get("name", "")), 14, 600, x1 - lx - 30 - pw_), 14, 600, TEXT, anchor="lm")
            p.text((x1, mid), ptxt, 14, 600, TEXT, anchor="rm")
            ly += 22
            kids = sorted(b.get("children") or [], key=lambda c: -float(c.get("pct", 0)))
            if len(kids) >= 2:  # a single child is not a breakdown
                tx, kx = lx + 5, lx + 22
                top = last = ly - 3
                for c in kids:
                    cm = last = ly + 9
                    p.line(tx, cm, kx - 6, cm, fill=branch, width=1.25)
                    cpt = fmt_pct(float(c.get("pct", 0)))
                    cw_ = p.tw(cpt, 12, 500)
                    p.text((kx, cm), p.ellipsize(str(c.get("name", "")), 12, 450, x1 - kx - cw_ - 12), 12, 450, MUTED, anchor="lm")
                    p.text((x1, cm), cpt, 12, 500, MUTED, anchor="rm")
                    ly += 20
                p.line(tx, top, tx, last, fill=branch, width=1.25)
                ly += 6
            ly += 6
        y = max(top0 + D + cap_h, ly - 6) + 20
    else:
        p.text((x0, y), "No breakdown available", 13, 450, MUTED)
        y += 24
    y += IN - 24
    p.cards.append((card2_top, y))
    return y


def draw(d):
    pre = Painter(1600)
    card_bottom = int(round(render(d, pre)))
    pre.cards[-1] = (pre.cards[-1][0], card_bottom)
    H = card_bottom + PAD_B
    p = Painter(H)
    for top, bot in pre.cards:
        p.rrect((PAD_X, top, W - PAD_X - 1 / K, bot - 1 / K), 22, fill=CARD, outline=LINE, width=1)
    render(d, p)
    if d.get("generated_label"):
        p.text((W / 2, card_bottom + PAD_B / 2), f"Generated {d['generated_label']}", 11, 450, FAINT, anchor="mm")
    return p.img.resize((int(round(W * OUT_SCALE)), int(round(H * OUT_SCALE))), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", nargs="?", default="-", help="JSON file path, or - for stdin")
    ap.add_argument("--out", default="/workspace/usage_card.png")
    ap.add_argument("--layout", choices=["lines", "plain", "split"], help="overrides JSON 'layout' (default lines)")
    ap.add_argument("--theme", choices=["light", "dark"], help="overrides JSON 'theme' (default light)")
    ap.add_argument("--version", action="version", version=VERSION)
    a = ap.parse_args()
    data = json.load(sys.stdin if a.input == "-" else open(a.input))
    theme = apply_theme(a.theme or data.get("theme"))
    layout = (a.layout or data.get("layout") or "lines").lower()
    if layout not in ("lines", "plain", "split"):
        raise SystemExit(f"unknown layout {layout!r}; use lines, plain or split")
    data["_layout"] = layout
    img = draw(data)
    img.save(a.out, optimize=True)
    m = compute(data)
    print(json.dumps({"out": a.out, "version": VERSION, "theme": theme, "layout": layout, "size": img.size,
                      "verdict": m["verdict"], "detail": m["detail"], "time_left": m["left_dh"],
                      "rate_pct_per_h": m["rate"], "rate_pct_per_day": m["rate"] * 24 if m["rate"] is not None else None,
                      "ideal_now": m["ideal"], "projected": m["projected"]}))


if __name__ == "__main__":
    main()
