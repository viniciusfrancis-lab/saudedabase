"""
app_turma_hud.py — Saúde da Base de Turmas com tema HUD futurista (v2: painel denso + carrossel 3D).

Não altera o app_turma.py: importa o módulo, troca paleta + CSS, injeta um "palco" central
(medidor de anéis + telemetria lateral, só com dados reais) logo após o banner e chama render().
Rodar:  streamlit run app_turma_hud.py
"""

import base64
import html
import json
import random
import re
from functools import lru_cache
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# Impede o app_turma de se auto-executar no import (ele checa esse atributo).
st._is_running_with_vitrine = True

import app_turma as base  # noqa: E402

# ── Paleta HUD ────────────────────────────────────────────────────────────────
CYAN, AMBER, RED, GREEN = "#00e5ff", "#ffb300", "#ff3b5c", "#00e5a0"
BG, PANEL, LINE = "#050b14", "#0a1626", "#12384a"

TEXT, MUTED = "#cfefff", "#7fb3c7"

# Constantes do app_turma que o render() lê em tempo de execução. São aplicadas só durante
# render() e restauradas depois, para não contaminar outros painéis no vitrine.
_OVERRIDES = {
    "YELLOW_DARK": "#06344a",  # cabeçalho da tabela de detalhamento
    "TEAL": CYAN,              # linha "Turmas com alerta" do gráfico de evolução
    "PRIO_LOW": GREEN,
    "PRIO_HIGH": RED,
    "TEXT": TEXT,
    "MUTED": MUTED,
}

fmt = base.fmt


# ── Banner J.A.R.V.I.S. (texto em HTML, fundo = imagem SEM texto ou circuitos em SVG) ──
BANNER_TITULO    = "J.A.R.V.I.S."
BANNER_SUBTITULO = "Jornada de Acompanhamento, Revisão e Validação de Informações do SEGES"

# Imagem de fundo SEM texto, na mesma pasta do app. Se for None, procura os nomes abaixo;
# se não achar nenhum, usa um fundo de circuitos gerado em SVG (não depende de arquivo).
BANNER_BG = None  # ex.: "banner_bg.png"
_BANNER_CANDIDATOS = ["banner_bg.png", "banner_bg.jpg", "banner_jarvis.png", "banner_jarvis.jpg",
                      "banner.png", "banner.jpg", "banner.jpeg", "banner.webp"]
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _circuit_svg_uri(W: int = 1600, H: int = 240, n: int = 46) -> str:
    """Fundo de circuitos determinístico (mesma imagem a cada execução)."""
    rnd = random.Random(7)
    lines = []
    for _ in range(n):
        x, y = rnd.randint(0, W), rnd.randint(12, H - 12)
        pts = [(x, y)]
        for _ in range(rnd.randint(2, 4)):
            dx = rnd.choice([-1, 1]) * rnd.randint(40, 180)
            x += dx
            pts.append((x, y))
            dy = rnd.choice([-1, 1]) * rnd.randint(15, 60)
            if not 8 < y + dy < H - 8:
                dy = -dy
            x += abs(dy) * (1 if dx > 0 else -1)
            y += dy
            pts.append((x, y))
        op = rnd.choice([0.18, 0.28, 0.4])
        poly = " ".join(f"{px},{py}" for px, py in pts)
        lines.append(f'<polyline points="{poly}" fill="none" stroke="#00e5ff" stroke-opacity="{op}" stroke-width="1"/>')
        for px, py in (pts[0], pts[-1]):
            lines.append(f'<circle cx="{px}" cy="{py}" r="2.6" fill="#00e5ff" fill-opacity="{min(op + .35, .85)}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice">'
           + "".join(lines) + "</svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


@lru_cache(maxsize=1)
def _banner_bg_uri() -> str:
    nomes = [BANNER_BG] if BANNER_BG else _BANNER_CANDIDATOS
    for nome in nomes:
        for pasta in (base._BASE, Path.cwd()):
            p = pasta / nome
            if p.is_file() and p.suffix.lower() in _MIME:
                return f"data:{_MIME[p.suffix.lower()]};base64," + base64.b64encode(p.read_bytes()).decode()
    return _circuit_svg_uri()


# ── Fundo da PÁGINA inteira (imagem fixa atrás de tudo) ───────────────────────
# Use uma imagem SEM texto. Se for None, procura os nomes abaixo na pasta do app;
# se não achar, usa circuitos em SVG em tela cheia. Trocou a imagem? Reinicie o streamlit.
PAGE_BG = None      # ex.: "fundo.png"
PAGE_BG_DIM = 0.45  # 0 = imagem pura · 1 = tudo escuro. Aumente se atrapalhar a leitura.
_PAGE_CANDIDATOS = ["page_bg.png", "page_bg.jpg", "fundo.png", "fundo.jpg", "fundo.webp",
                    "fundo_jarvis.png", "fundo_jarvis.jpg", "background.png", "background.jpg",
                    "bg.png", "bg.jpg", "bg.webp"]


@lru_cache(maxsize=1)
def _page_bg_uri() -> str:
    nomes = [PAGE_BG] if PAGE_BG else _PAGE_CANDIDATOS
    for nome in nomes:
        for pasta in (base._BASE, Path.cwd()):
            p = pasta / nome
            if p.is_file() and p.suffix.lower() in _MIME:
                return f"data:{_MIME[p.suffix.lower()]};base64," + base64.b64encode(p.read_bytes()).decode()
    return _circuit_svg_uri(1920, 1080, 230)


def _page_bg_layers() -> str:
    dim = f"rgba(5,11,20,{PAGE_BG_DIM})"
    return (f"radial-gradient(circle at 50% 38%, #0b2f4566 0%, transparent 42%), "
            f"linear-gradient({dim}, {dim}), "
            f"url({_page_bg_uri()}) center / cover no-repeat fixed, "
            f"{BG}")


def _banner_html() -> str:
    return (f'<div class="hud-banner" style="background-image:url({_banner_bg_uri()});">'
            f'<div class="hud-banner-t1">{BANNER_TITULO}</div>'
            '<div class="hud-banner-line"></div>'
            f'<div class="hud-banner-t2">{BANNER_SUBTITULO}</div></div>')


# ── Palco central: medidor de anéis + telemetria (dados reais do pipeline) ────
def _gauge_svg(pct, qa, qm, ql, total):
    tot = max(total, 1)
    a, m, l = (qa / tot * 100, qm / tot * 100, ql / tot * 100)
    p = min(max(pct or 0, 0), 100)

    def arc(r, w, color, start, size, glow=True):
        f = ' filter="url(#glow)"' if glow else ""
        return (f'<circle cx="150" cy="150" r="{r}" fill="none" stroke="{color}" stroke-width="{w}" '
                f'pathLength="100" stroke-dasharray="{size:.2f} {100 - size:.2f}" '
                f'stroke-dashoffset="{-start:.2f}" transform="rotate(-90 150 150)"{f}/>')

    pct_txt = f"{p:.1f}% DAS TURMAS ATIVAS" if pct is not None else "TURMAS ATIVAS INDISPONÍVEL"
    return "".join([
        '<svg viewBox="0 0 300 300" class="hud-gauge" xmlns="http://www.w3.org/2000/svg">',
        '<defs><filter id="glow" x="-30%" y="-30%" width="160%" height="160%">'
        '<feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/>'
        '<feMergeNode in="SourceGraphic"/></feMerge></filter></defs>',
        f'<circle class="spin-a" cx="150" cy="150" r="146" fill="none" stroke="{CYAN}" stroke-opacity=".45" stroke-width="1" stroke-dasharray="3 7"/>',
        f'<circle class="spin-b" cx="150" cy="150" r="136" fill="none" stroke="{CYAN}" stroke-opacity=".55" stroke-width="9" stroke-dasharray="1.2 4.2"/>',
        f'<circle cx="150" cy="150" r="122" fill="none" stroke="{CYAN}" stroke-opacity=".12" stroke-width="9"/>',
        arc(122, 9, CYAN, 0, p),
        f'<circle cx="150" cy="150" r="106" fill="none" stroke="{CYAN}" stroke-opacity=".25" stroke-width="1"/>',
        f'<circle cx="150" cy="150" r="98" fill="none" stroke="{CYAN}" stroke-opacity=".10" stroke-width="7"/>',
        arc(98, 7, RED, 0, a),
        arc(98, 7, AMBER, a, m),
        arc(98, 7, GREEN, a + m, l),
        f'<circle class="spin-a" cx="150" cy="150" r="80" fill="{BG}" fill-opacity=".85" stroke="{CYAN}" stroke-opacity=".5" stroke-width="1" stroke-dasharray="14 4 2 4"/>',
        f'<text x="150" y="150" text-anchor="middle" class="g-num">{fmt(total)}</text>',
        '<text x="150" y="172" text-anchor="middle" class="g-lbl">TURMAS COM ALERTA</text>',
        f'<text x="150" y="190" text-anchor="middle" class="g-sub">{pct_txt}</text>',
        '</svg>',
    ])


def _tile(label, value, bar=None, tone="cyan"):
    barh = f'<div class="hud-tile-bar {tone}"><i style="width:{min(max(bar, 0), 100):.0f}%"></i></div>' if bar is not None else ""
    return (f'<div class="hud-tile {tone}"><span class="hud-tile-l">{label}</span>'
            f'<span class="hud-tile-v">{value}</span>{barh}</div>')


def _stage_html():
    df = base._carregar_resumo_turma()
    if df.empty:
        return ""
    total = int(df["qtd"].sum())
    pr = df.groupby("prioridade")["qtd"].sum()
    qa, qm, ql = int(pr.get("alta", 0)), int(pr.get("média", 0)), int(pr.get("baixa", 0))

    ativas = base._carregar_total_turmas()
    pct = (total / ativas * 100) if ativas else None

    reg = base._carregar_excedentes_regional()
    exc = int(reg["excedentes"].sum()) if not reg.empty else None
    n_reg = int((reg["excedentes"] > 0).sum()) if not reg.empty else None
    turmas_exc = int(reg["turmas"].sum()) if not reg.empty else None
    top_reg = reg.iloc[0]["regional"] if not reg.empty else "—"
    top_reg_v = int(reg.iloc[0]["excedentes"]) if not reg.empty else 0
    top_share = (top_reg_v / exc * 100) if exc else None

    left = "".join([
        _tile("Turmas ativas", fmt(ativas) if ativas else "—", 100 if ativas else None),
        _tile("Turmas com alerta", fmt(total), pct, "amber"),
        _tile("% de turmas afetadas", f"{pct:.1f}%" if pct is not None else "—", pct, "amber"),
    ])
    right = "".join([
        _tile("Professores excedentes", fmt(exc) if exc is not None else "—", 100 if exc else None, "red"),
        _tile("Regionais afetadas", fmt(n_reg) if n_reg is not None else "—", None, "red"),
        _tile(f"Maior concentração · {top_reg}", f"{top_share:.1f}%" if top_share is not None else "—", top_share, "red"),
    ])
    legend = (f'<div class="hud-legend"><span><b style="background:{RED}"></b>Alta {fmt(qa)}</span>'
              f'<span><b style="background:{AMBER}"></b>Média {fmt(qm)}</span>'
              f'<span><b style="background:{GREEN}"></b>Baixa {fmt(ql)}</span></div>')

    return ('<p class="freq-section-title" style="margin-top:1.25rem;">centro de comando</p>'
            f'<div class="hud-stage"><div class="hud-side">{left}</div>'
            f'<div class="hud-core">{_gauge_svg(pct, qa, qm, ql, total)}{legend}</div>'
            f'<div class="hud-side">{right}</div></div>')


# ── Carrossel 3D da "visão geral" ─────────────────────────────────────────────
# <script> não roda em st.markdown, então o carrossel vive num iframe (components.html).
# Os cards são lidos do próprio HTML que o app_turma gerou (grid), sem tocar nos dados.
_CARD_RE = re.compile(
    r'<div class="freq-card[^"]*"><div class="freq-card-top">'
    r'<span class="freq-card-icon">(.*?)</span><span class="freq-card-badge (\w+)">(.*?)</span></div>'
    r'<p class="freq-card-label"[^>]*>(.*?)</p><p class="freq-card-value[^"]*">(.*?)</p></div>', re.S)
_PRIO_COR = {"high": RED, "med": AMBER, "low": GREEN}

_CAROUSEL_DOC = """<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;background:transparent;color:__TEXT__;font-family:'Segoe UI',system-ui,sans-serif;overflow:hidden}
#wrap{position:relative;height:__H__px;user-select:none;-webkit-user-select:none}
#stage{position:absolute;left:0;right:0;top:0;height:250px;perspective:1100px;cursor:grab;touch-action:pan-y;
  background:radial-gradient(ellipse at 50% 85%,__CYAN__22,transparent 62%)}
#stage.drag{cursor:grabbing}
#ring{position:absolute;left:50%;top:48%;width:0;height:0;transform-style:preserve-3d}
#floor{position:absolute;left:50%;bottom:6px;width:640px;height:90px;margin-left:-320px;border-radius:50%;
  border:1px solid __CYAN__55;transform:rotateX(72deg);box-shadow:0 0 30px __CYAN__33,inset 0 0 30px __CYAN__22;pointer-events:none}
.c{position:absolute;width:196px;height:124px;margin:-62px 0 0 -98px;padding:12px 14px;border:1px solid var(--k);
  background:linear-gradient(160deg,__PANEL__ee,#050b14ee);box-shadow:0 0 14px var(--k)44,inset 0 0 18px var(--k)18;
  backface-visibility:hidden;-webkit-backface-visibility:hidden;border-radius:4px;display:flex;flex-direction:column;justify-content:space-between}
.c.f{box-shadow:0 0 28px var(--k)99,inset 0 0 22px var(--k)33}
.top{display:flex;justify-content:space-between;align-items:center}
.ic{font-size:20px}.bd{font-size:10px;letter-spacing:.14em;padding:2px 7px;border:1px solid var(--k);color:var(--k);border-radius:10px}
.lb{margin:0;font-size:12px;line-height:1.25;color:__MUTED__;max-height:30px;overflow:hidden}
.vl{margin:0;font-size:30px;font-weight:700;color:var(--k);text-shadow:0 0 12px var(--k);font-variant-numeric:tabular-nums}
#info{position:absolute;left:0;right:0;top:262px;text-align:center}
#info .n{font-size:15px;color:__TEXT__}#info .v{font-size:12px;color:__MUTED__;margin-top:3px;letter-spacing:.08em}
#dots{position:absolute;left:0;right:0;top:318px;display:flex;justify-content:center;gap:8px;flex-wrap:wrap;padding:0 8px}
.d{width:11px;height:11px;border-radius:50%;border:1px solid var(--k);background:transparent;cursor:pointer;padding:0}
.d.on{background:var(--k);box-shadow:0 0 9px var(--k)}
#tg{position:absolute;right:6px;top:4px;z-index:5;background:#050b14cc;color:__CYAN__;border:1px solid __CYAN__77;
  font:600 10px 'Segoe UI',sans-serif;letter-spacing:.14em;padding:5px 9px;cursor:pointer;border-radius:3px}
#hint{position:absolute;left:8px;top:6px;font-size:10px;letter-spacing:.14em;color:__MUTED__;pointer-events:none}
#grid{display:none;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;padding:34px 4px 4px;height:__H__px;overflow:auto}
#grid .c{position:relative;margin:0;width:auto;height:112px;backface-visibility:visible}
.grid #stage,.grid #info,.grid #dots,.grid #hint{display:none}.grid #grid{display:grid}
</style></head><body><div id="wrap">
<button id="tg">VER GRADE</button><div id="hint">ARRASTE · CLIQUE · ← →</div>
<div id="stage"><div id="floor"></div><div id="ring"></div></div>
<div id="info"><div class="n" id="n"></div><div class="v" id="v"></div></div><div id="dots"></div><div id="grid"></div>
</div><script>
const D=__DATA__,N=D.length,STEP=360/N;
const ring=document.getElementById('ring'),stage=document.getElementById('stage'),dots=document.getElementById('dots');
const R=Math.max(300,Math.round(innerWidth*0.36));
function card(d){return '<div class="top"><span class="ic">'+d.i+'</span><span class="bd">'+d.b+'</span></div><p class="lb" title="'+d.l.replace(/<[^>]*>/g,'')+'">'+d.l+'</p><p class="vl">'+d.v+'</p>';}
const els=D.map((d,i)=>{const e=document.createElement('div');e.className='c';e.style.setProperty('--k',d.k);e.innerHTML=card(d);
  e.onclick=()=>{if(!moved)go(i)};ring.appendChild(e);return e;});
const dts=D.map((d,i)=>{const b=document.createElement('button');b.className='d';b.style.setProperty('--k',d.k);
  b.title=d.l.replace(/<[^>]*>/g,'');b.onclick=()=>go(i);dots.appendChild(b);return b;});
document.getElementById('grid').innerHTML=D.map(d=>'<div class="c" style="--k:'+d.k+'">'+card(d)+'</div>').join('');
let th=0,tg=0,drag=false,moved=false,sx=0,st0=0,vel=0,lx=0,last=0,idle=Date.now(),hover=false,front=-1;
const mod=(a,m)=>((a%m)+m)%m;
function go(i){const dl=mod(-i*STEP-th+180,360)-180;tg=th+dl;idle=Date.now();}
function snap(){tg=Math.round(tg/STEP)*STEP;}
stage.addEventListener('pointerdown',e=>{drag=true;moved=false;sx=lx=e.clientX;st0=th;vel=0;stage.classList.add('drag');stage.setPointerCapture(e.pointerId);idle=Date.now();});
stage.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-sx;if(Math.abs(dx)>5)moved=true;
  th=st0+dx*0.35;tg=th;vel=(e.clientX-lx)*0.35;lx=e.clientX;});
function up(){if(!drag)return;drag=false;stage.classList.remove('drag');tg=th+vel*6;snap();idle=Date.now();setTimeout(()=>moved=false,0);}
stage.addEventListener('pointerup',up);stage.addEventListener('pointercancel',up);
stage.addEventListener('mouseenter',()=>hover=true);stage.addEventListener('mouseleave',()=>hover=false);
stage.addEventListener('wheel',e=>{if(Math.abs(e.deltaX)>Math.abs(e.deltaY)||e.shiftKey){e.preventDefault();
  const t=Date.now();if(t-last>140){last=t;tg=Math.round(tg/STEP)+((e.deltaX||e.deltaY)>0?-1:1);tg*=STEP;idle=t;}}},{passive:false});
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight'){tg=(Math.round(tg/STEP)-1)*STEP;idle=Date.now();}
  if(e.key==='ArrowLeft'){tg=(Math.round(tg/STEP)+1)*STEP;idle=Date.now();}});
document.getElementById('tg').onclick=function(){const g=document.body.classList.toggle('grid');this.textContent=g?'VER CARROSSEL':'VER GRADE';};
function frame(){
  if(!drag){th+=(tg-th)*0.12;if(Math.abs(tg-th)<0.01)th=tg;}
  if(!drag&&!hover&&Date.now()-idle>6000&&Math.abs(tg-th)<0.5){tg-=STEP;idle=Date.now()-3000;}
  ring.style.transform='translateZ(-'+R+'px) rotateX(-6deg)';
  for(let i=0;i<N;i++){const a=i*STEP+th,c=Math.cos(a*Math.PI/180),o=0.18+0.82*Math.max(0,(c+1)/2);
    els[i].style.transform='rotateY('+a+'deg) translateZ('+R+'px)';els[i].style.opacity=o.toFixed(3);
    els[i].style.zIndex=Math.round(c*100)+100;}
  const f=mod(Math.round(-th/STEP),N);
  if(f!==front){front=f;els.forEach((e,i)=>e.classList.toggle('f',i===f));dts.forEach((b,i)=>b.classList.toggle('on',i===f));
    const d=D[f];document.getElementById('n').innerHTML=d.i+' '+d.l;
    document.getElementById('v').innerHTML=d.v+' · PRIORIDADE '+d.b+' · '+(f+1)+'/'+N;}
  requestAnimationFrame(frame);}
frame();
</script></body></html>"""


def _carousel_doc(cards_html: str):
    cards = [dict(i=m[0], k=_PRIO_COR.get(m[1], CYAN), b=m[2], l=m[3], v=m[4]) for m in _CARD_RE.findall(cards_html)]
    if len(cards) < 3:
        return None
    data = json.dumps(cards, ensure_ascii=False).replace("</", "<\\/")
    doc = _CAROUSEL_DOC
    for k, v in {"__DATA__": data, "__H__": "340", "__TEXT__": TEXT, "__MUTED__": MUTED,
                 "__CYAN__": CYAN, "__PANEL__": PANEL}.items():
        doc = doc.replace(k, v)
    return doc


# Injeta banner e palco no render() monolítico do app_turma.
def _make_md(orig):
    def _md(body, *args, **kwargs):
        if isinstance(body, str) and 'class="freq-header"' in body:
            orig(_banner_html(), unsafe_allow_html=True)  # banner antes do cabeçalho
        if isinstance(body, str) and 'class="freq-cards-grid"' in body:
            try:  # carrossel 3D; se algo falhar, cai no grid original
                doc = _carousel_doc(body)
                if doc:
                    components.html(doc, height=345)
                    return
            except Exception:
                pass
        orig(body, *args, **kwargs)
        if isinstance(body, str) and 'class="freq-banner"' in body:
            try:
                palco = _stage_html()
            except Exception as e:  # o palco nunca deve derrubar o painel
                palco = f'<p class="freq-section-title">centro de comando indisponível: {html.escape(str(e))}</p>'
            if palco:
                orig(palco, unsafe_allow_html=True)
    return _md


# Os gráficos do app_turma têm grade/eixos claros fixos (#f0f4f5): sobre painel escuro viram
# linhas brancas. Este wrapper reescreve só as cores, sem mexer nos dados nem no layout.
def _make_plotly(orig):
    def _pc(fig, *args, **kwargs):
        try:
            fig.update_layout(font=dict(color=MUTED), legend=dict(font=dict(color=TEXT)))
            fig.update_xaxes(gridcolor=LINE, linecolor=LINE, tickfont=dict(color=TEXT))
            fig.update_yaxes(gridcolor=LINE, tickfont=dict(color=TEXT))
        except Exception:
            pass
        return orig(fig, *args, **kwargs)
    return _pc


# ── CSS ───────────────────────────────────────────────────────────────────────
def _brackets(color, size=12, w=2):
    g = f"linear-gradient({color},{color})"
    layers = [
        (f"{size}px {w}px", "0 0"), (f"{w}px {size}px", "0 0"),
        (f"{size}px {w}px", "100% 0"), (f"{w}px {size}px", "100% 0"),
        (f"{size}px {w}px", "0 100%"), (f"{w}px {size}px", "0 100%"),
        (f"{size}px {w}px", "100% 100%"), (f"{w}px {size}px", "100% 100%"),
    ]
    return (f"background-image:{','.join([g] * 8)};"
            f"background-size:{','.join(s for s, _ in layers)};"
            f"background-position:{','.join(p for _, p in layers)};"
            "background-repeat:no-repeat;")


HUD_CSS = f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Orbitron:wght@500;700&display=swap');

  .stApp {{
    background: {_page_bg_layers()} !important;
    font-family: 'Rajdhani', 'Segoe UI', sans-serif;
    color: {TEXT};
  }}
  /* Scanlines + varredura */
  .stApp::after {{
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 9999;
    background:
      linear-gradient(180deg, transparent 0%, {CYAN}10 50%, transparent 100%) 0 -30vh / 100% 30vh no-repeat,
      repeating-linear-gradient(0deg, {CYAN}08 0 1px, transparent 1px 3px);
    animation: sweep 7s linear infinite;
  }}
  @keyframes sweep {{ to {{ background-position: 0 130vh, 0 0; }} }}

  .stApp p, .stApp label, .stApp span, .stApp li {{ color: {TEXT}; }}
  code {{ color: {CYAN} !important; background: #0a1626 !important; }}

  /* Banner J.A.R.V.I.S. — duas linhas separadas */
  .hud-banner {{
    position: relative; text-align: center; padding: 30px 24px 26px; margin-bottom: 10px; overflow: hidden;
    background-size: cover; background-position: center; background-color: {BG};
    border: 1px solid {CYAN}55; box-shadow: 0 0 22px {CYAN}33, inset 0 0 40px {BG}cc;
  }}
  .hud-banner::before {{ content: ""; position: absolute; inset: 0; pointer-events: none;
    background: radial-gradient(ellipse at center, {BG}80 0%, {BG}d0 75%); }}
  .hud-banner::after {{ content: ""; position: absolute; inset: 0; pointer-events: none; {_brackets(CYAN, 18, 2)} }}
  .hud-banner-t1 {{
    position: relative; z-index: 1; font-family: 'Orbitron', 'Rajdhani', sans-serif; font-weight: 700;
    font-size: clamp(34px, 5vw, 68px); letter-spacing: .2em; line-height: 1.1;
    color: {CYAN} !important; text-shadow: 0 0 14px {CYAN}, 0 0 34px {CYAN}88;
  }}
  .hud-banner-line {{
    position: relative; z-index: 1; height: 2px; width: min(60%, 640px); margin: 12px auto;
    background: linear-gradient(90deg, transparent, {CYAN}, transparent); box-shadow: 0 0 10px {CYAN};
  }}
  .hud-banner-t2 {{
    position: relative; z-index: 1; font-family: 'Rajdhani', sans-serif; font-weight: 600;
    font-size: clamp(14px, 2vw, 26px); letter-spacing: .06em;
    color: {TEXT} !important; text-shadow: 0 0 8px {CYAN}88;
  }}

  /* Header */
  .freq-header {{
    background: linear-gradient(90deg, #06222f 0%, #0a1626 100%) !important;
    border: 1px solid {CYAN}66; box-shadow: 0 0 18px {CYAN}33, inset 0 0 20px {CYAN}12;
    border-radius: 4px !important;
    clip-path: polygon(0 0, calc(100% - 18px) 0, 100% 18px, 100% 100%, 18px 100%, 0 calc(100% - 18px));
  }}
  .freq-header-divider {{ background: {CYAN}66 !important; }}
  .freq-header-title {{
    font-family: 'Orbitron', 'Rajdhani', sans-serif !important; letter-spacing: .12em;
    text-transform: uppercase; color: {CYAN} !important; text-shadow: 0 0 10px {CYAN}99;
  }}
  .freq-header-sub {{ color: {MUTED} !important; letter-spacing: .18em; text-transform: uppercase; }}
  .freq-badge {{ border: 1px solid {CYAN}55; background: {CYAN}14 !important; color: {CYAN} !important; font-family: 'Orbitron', monospace; }}
  .freq-dot {{ background: {GREEN} !important; box-shadow: 0 0 8px {GREEN}; animation: hudpulse 1.6s infinite; }}
  @keyframes hudpulse {{ 50% {{ opacity: .25; }} }}

  /* Banner */
  .freq-banner {{
    background: linear-gradient(135deg, #0a1626 0%, #0c2c3f 100%) !important;
    border: 1px solid {AMBER}77; box-shadow: 0 0 16px {AMBER}22; border-radius: 4px !important; margin-top: 10px;
  }}
  .freq-banner-num {{ font-family: 'Orbitron', monospace !important; color: {AMBER} !important; text-shadow: 0 0 12px {AMBER}aa; font-size: 30px !important; }}
  .freq-banner-label {{ color: {MUTED} !important; letter-spacing: .12em; text-transform: uppercase; }}
  .freq-chip {{ background: {CYAN}10 !important; border: 1px solid {CYAN}44; border-radius: 3px !important; }}
  .freq-chip-num {{ color: {CYAN} !important; font-family: 'Orbitron', monospace; }}
  .freq-chip-label {{ color: {MUTED} !important; }}
  .freq-chip:nth-child(1) .freq-chip-dot {{ background: {RED} !important; box-shadow: 0 0 6px {RED}; }}
  .freq-chip:nth-child(2) .freq-chip-dot {{ background: {AMBER} !important; box-shadow: 0 0 6px {AMBER}; }}
  .freq-chip:nth-child(3) .freq-chip-dot {{ background: {GREEN} !important; box-shadow: 0 0 6px {GREEN}; }}

  /* Seções */
  .freq-section-title {{
    color: {CYAN} !important; border-bottom: 1px solid {CYAN}55 !important;
    font-family: 'Orbitron', monospace; letter-spacing: .2em; font-size: 11px !important;
  }}
  .freq-section-title::before {{ content: "▌"; color: {AMBER}; margin-right: 8px; }}

  /* ── Palco central ── */
  .hud-stage {{ display: grid; grid-template-columns: 1fr 360px 1fr; gap: 22px; align-items: center; margin: 8px 0 18px; }}
  .hud-side {{ display: flex; flex-direction: column; gap: 12px; }}
  .hud-core {{ display: flex; flex-direction: column; align-items: center; }}
  .hud-gauge {{ width: 100%; max-width: 340px; filter: drop-shadow(0 0 14px {CYAN}55); }}
  .hud-gauge .spin-a {{ transform-box: fill-box; transform-origin: center; animation: spin 40s linear infinite; }}
  .hud-gauge .spin-b {{ transform-box: fill-box; transform-origin: center; animation: spin 60s linear infinite reverse; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .hud-gauge .g-num {{ font-family: 'Orbitron', monospace; font-size: 38px; font-weight: 700; fill: {CYAN}; filter: drop-shadow(0 0 6px {CYAN}); }}
  .hud-gauge .g-lbl {{ font-family: 'Rajdhani', sans-serif; font-size: 11px; letter-spacing: .22em; fill: {MUTED}; }}
  .hud-gauge .g-sub {{ font-family: 'Rajdhani', sans-serif; font-size: 9px; letter-spacing: .14em; fill: {AMBER}; }}
  .hud-legend {{ display: flex; gap: 18px; margin-top: 2px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: .08em; }}
  .hud-legend span {{ color: {TEXT}; display: flex; align-items: center; gap: 6px; }}
  .hud-legend b {{ width: 9px; height: 9px; display: inline-block; box-shadow: 0 0 6px currentColor; }}

  .hud-tile {{
    position: relative; background: {PANEL}; border: 1px solid {CYAN}22; padding: 12px 16px 12px;
    display: grid; grid-template-columns: 1fr auto; row-gap: 8px; align-items: baseline;
    box-shadow: inset 0 0 18px {CYAN}0d;
  }}
  .hud-tile::before {{ content: ""; position: absolute; inset: -1px; pointer-events: none; {_brackets(CYAN)} }}
  .hud-tile.amber::before {{ {_brackets(AMBER)} }}
  .hud-tile.red::before   {{ {_brackets(RED)} }}
  .hud-tile-l {{ font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: {MUTED}; }}
  .hud-tile-v {{ font-family: 'Orbitron', monospace; font-size: 24px; font-weight: 700; color: {CYAN}; text-shadow: 0 0 10px {CYAN}77; }}
  .hud-tile.amber .hud-tile-v {{ color: {AMBER}; text-shadow: 0 0 10px {AMBER}77; }}
  .hud-tile.red .hud-tile-v   {{ color: {RED};   text-shadow: 0 0 10px {RED}77; }}
  .hud-tile-bar {{ grid-column: 1 / -1; height: 4px; background: {CYAN}18; position: relative; overflow: hidden; }}
  .hud-tile-bar i {{ display: block; height: 100%; background: {CYAN}; box-shadow: 0 0 8px {CYAN}; }}
  .hud-tile-bar.amber i {{ background: {AMBER}; box-shadow: 0 0 8px {AMBER}; }}
  .hud-tile-bar.red i   {{ background: {RED};   box-shadow: 0 0 8px {RED}; }}

  /* Cards */
  .freq-card {{
    background: {PANEL} !important; border: 1px solid {CYAN}33 !important; border-top: 3px solid {AMBER} !important;
    border-radius: 3px !important; box-shadow: inset 0 0 18px {CYAN}0d;
  }}
  .freq-card::before {{ content: ""; position: absolute; inset: 0; pointer-events: none; {_brackets(CYAN, 9, 1)} }}
  .freq-card::after {{ background: {AMBER}1f !important; opacity: 1 !important; }}
  .freq-card.warn {{ border-top-color: {RED} !important; }}
  .freq-card.warn::after {{ background: {RED}22 !important; }}
  .freq-card.ok {{ border-top-color: {GREEN} !important; }}
  .freq-card.ok::after {{ background: {GREEN}22 !important; }}
  .freq-card:hover {{ box-shadow: 0 0 22px {CYAN}55, inset 0 0 18px {CYAN}18 !important; }}
  .freq-card-label {{ color: {MUTED} !important; letter-spacing: .06em; text-transform: uppercase; }}
  .freq-card-value {{ color: {CYAN} !important; font-family: 'Orbitron', monospace; text-shadow: 0 0 10px {CYAN}88; }}
  .freq-card-value.warn {{ color: {RED} !important; text-shadow: 0 0 10px {RED}88; }}
  .freq-card-badge.high, .pill.high {{ background: {RED}26 !important; color: {RED} !important; border: 1px solid {RED}66; }}
  .freq-card-badge.med,  .pill.med  {{ background: {AMBER}26 !important; color: {AMBER} !important; border: 1px solid {AMBER}66; }}
  .freq-card-badge.low,  .pill.low  {{ background: {GREEN}26 !important; color: {GREEN} !important; border: 1px solid {GREEN}66; }}

  .freq-placeholder {{ background: {PANEL} !important; border: 1.5px dashed {CYAN}77 !important; color: {CYAN} !important; border-radius: 4px !important; }}

  /* Gráficos */
  div[data-testid="stPlotlyChart"] {{ position: relative; background: {PANEL} !important; border: 1px solid {CYAN}22; border-radius: 2px !important; padding: 10px; }}
  div[data-testid="stPlotlyChart"]::before {{ content: ""; position: absolute; inset: -1px; pointer-events: none; {_brackets(CYAN)} }}

  /* Iframe (carrossel 3D): moldura HUD */
  div[data-testid="stIFrame"] iframe, iframe[title="st.iframe"] {{
    border: 1px solid {CYAN}55 !important; border-radius: 3px !important; box-shadow: 0 0 16px {CYAN}33;
  }}

  /* Tabela */
  .stApp table td {{ background: {PANEL} !important; color: {TEXT} !important; border-bottom: 1px solid {LINE} !important; }}
  .stApp table tr:hover td {{ background: #0e2a3d !important; }}
  .stApp table th {{ color: {CYAN} !important; background: #06222f !important; border-bottom: 2px solid {CYAN}88; font-family: 'Orbitron', monospace; letter-spacing: .06em; }}
  .stApp div[style*="overflow:auto"] {{ background: {PANEL} !important; border: 1px solid {CYAN}44 !important; border-radius: 3px !important; }}

  /* Widgets */
  div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {{ background: {PANEL} !important; border-color: {CYAN}55 !important; color: {TEXT} !important; }}
  div[data-baseweb="select"] * {{ color: {TEXT} !important; }}
  ul[role="listbox"] {{ background: {PANEL} !important; }}
  .stDownloadButton button, .stButton button {{
    background: transparent !important; color: {CYAN} !important; border: 1px solid {CYAN} !important;
    border-radius: 3px !important; font-family: 'Orbitron', monospace; letter-spacing: .08em;
  }}
  .stDownloadButton button:hover, .stButton button:hover {{ background: {CYAN}22 !important; box-shadow: 0 0 12px {CYAN}77; }}
  div[data-testid="stCaptionContainer"] * {{ color: {MUTED} !important; }}
</style>
"""


# ── render() — mesmo contrato do app_turma.render(), para uso no vitrine ──────
def render():
    orig_md, orig_pc, orig_css = st.markdown, st.plotly_chart, base.CSS
    orig_consts = {k: getattr(base, k) for k in _OVERRIDES}
    try:
        for k, v in _OVERRIDES.items():
            setattr(base, k, v)
        base.CSS = orig_css + HUD_CSS
        st.markdown = _make_md(orig_md)
        st.plotly_chart = _make_plotly(orig_pc)
        base.render()
    finally:
        st.markdown = orig_md
        st.plotly_chart = orig_pc
        base.CSS = orig_css
        for k, v in orig_consts.items():
            setattr(base, k, v)


# ── Execução standalone ───────────────────────────────────────────────────────
if __name__ == "__main__":
    st.set_page_config(page_title="Saúde da Base de Turmas — SEDU", page_icon="🏫", layout="wide")
    try:
        render()
    except Exception as e:
        base.mostrar_erro(str(e))
