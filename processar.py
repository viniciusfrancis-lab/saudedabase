"""
processar.py — Orquestrador de validações da Base de Turmas
Executa todas as validações em sequência e consolida o resumo.parquet

O resumo.parquet é um HISTÓRICO EMPILHADO: cada execução acrescenta os alertas da base
lida, identificados pela coluna `dt_referencia` (dia da base do SEGES). Rodar de novo a
mesma base substitui apenas as linhas daquela data/validação; as demais datas ficam.

Uso:
    python processar.py
    python processar.py --force                   # regenera mesmo se a data já estiver no histórico
    python processar.py --sem-excel               # não gera os .xlsx por regional
    python processar.py --data-ref 15/10/2026     # força a dt_referencia (DD/MM/AAAA ou AAAA-MM-DD)
"""

import re
import shutil
import argparse
from pathlib import Path
from datetime import date, datetime

import polars as pl
from pygei.seges import turmas

# ── Caminhos ──────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
RESULTADOS   = BASE_DIR / "resultados"
RESUMO_PATH  = RESULTADOS / "resumo.parquet"            # histórico empilhado (todas as datas)
TOTAIS_PATH  = RESULTADOS / "totais.parquet"            # denominadores da base MAIS RECENTE lida (1 linha, formato antigo)
TOTAIS_HIST_PATH = RESULTADOS / "totais_historico.parquet"  # denominadores empilhados por dt_referencia
# .xlsx por regional (entrega para as SREs): na pasta do painel, ao lado de resultados/,
# em resultado_excel/DD_MM_AAAA (a data é a do dia em que o processar.py foi rodado).
EXCEL_BASE   = BASE_DIR / "resultado_excel"

DT_COL = "dt_referencia"

RESULTADOS.mkdir(parents=True, exist_ok=True)

# ── Registro de validações ────────────────────────────────────────────────────
# Cada validação exporta: NOME, ARQUIVO_SAIDA, COLUNAS_RESUMO, run(df_base) -> pl.DataFrame
# Ganchos opcionais: totais(df_base) -> dict | exportar_excel(df_resultado, df_base, pasta)
# Opcional: SCRIPT (id gravado na coluna `script`); se ausente usa o nome do módulo.
from validacoes import professores_excedentes

VALIDACOES = [
    professores_excedentes,
    # adicione novos módulos aqui
]

ANO_LETIVO = professores_excedentes.ANO_LETIVO


# ── Helpers ───────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def _script_id(modulo) -> str:
    return getattr(modulo, "SCRIPT", modulo.__name__.split(".")[-1])


def _extrair_data_texto(texto: str):
    """Procura uma data AAAAMMDD / AAAA-MM-DD / DDMMAAAA / DD_MM_AAAA em um texto."""
    candidatos = []
    for m in re.finditer(r"(?<!\d)(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)", texto):
        candidatos.append((m.group(1), m.group(2), m.group(3)))
    for m in re.finditer(r"(?<!\d)(\d{2})[-_.]?(\d{2})[-_.]?(\d{4})(?!\d)", texto):
        candidatos.append((m.group(3), m.group(2), m.group(1)))
    for a, mo, d in candidatos:
        try:
            dt = date(int(a), int(mo), int(d))
        except ValueError:
            continue
        if 2020 <= dt.year <= 2100:
            return dt
    return None


def resolver_data_referencia(override: str | None):
    """Dia da base do SEGES. Ordem: --data-ref > data no nome do arquivo/pasta > data de modificação."""
    if override:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(override, fmt).date(), "argumento --data-ref"
            except ValueError:
                pass
        raise SystemExit(f"--data-ref inválida: {override!r} (use DD/MM/AAAA ou AAAA-MM-DD)")

    caminho = Path(str(turmas.latest_path()))
    for texto in (caminho.stem, caminho.parent.name):
        d = _extrair_data_texto(texto)
        if d:
            return d, f"nome do arquivo/pasta ({texto})"
    return date.fromtimestamp(caminho.stat().st_mtime), "data de modificação do arquivo"


def carregar_base():
    """Base de turmas (turma x disciplina x professor) mais recente do SEGES, via pygei."""
    log(f"Lendo base de turmas: {turmas.latest_path()}")
    log("  (arquivo grande, pode levar alguns minutos)")
    df = turmas.latest()
    df = df.seges.por_ano(ANO_LETIVO)
    log(f"  {len(df):,} linhas (ano letivo {ANO_LETIVO})")
    return df


def carregar_historico(path: Path):
    """Lê um parquet histórico garantindo a coluna dt_referencia (tipo Date)."""
    if not path.exists():
        return None
    h = pl.read_parquet(path)
    if DT_COL not in h.columns:
        backup = path.with_name(f"{path.stem}_legado_{datetime.now():%Y%m%d_%H%M%S}.parquet")
        shutil.copy2(path, backup)
        log(f"  [AVISO] {path.name} não tem {DT_COL} (formato antigo). "
            f"Backup em {backup.name}; essas linhas ficam com {DT_COL} nulo.")
        return h.with_columns(pl.lit(None, dtype=pl.Date).alias(DT_COL))
    return h.with_columns(pl.col(DT_COL).cast(pl.Date))


def ja_processado(historico, script: str, dt_ref: date) -> bool:
    if historico is None or "script" not in historico.columns:
        return False
    return historico.filter(
        (pl.col("script") == script) & (pl.col(DT_COL) == dt_ref)
    ).height > 0


def _harmonizar(frame: pl.DataFrame) -> pl.DataFrame:
    # Evita SchemaError quando um módulo esquece de castar id_turma.
    COLUNAS_FORCAR_STRING = ["id_turma"]
    return frame.with_columns([
        pl.col(c).cast(pl.String, strict=False)
        for c in COLUNAS_FORCAR_STRING if c in frame.columns
    ])


def _concat(frames):
    try:
        return pl.concat(frames, how="diagonal_relaxed")
    except Exception:
        return pl.concat(frames, how="diagonal")


def _gravar_atomico(df: pl.DataFrame, destino: Path):
    tmp = destino.with_suffix(".tmp")
    df.write_parquet(tmp)
    tmp.replace(destino)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Regenera resultados mesmo se a dt_referencia já estiver no histórico")
    parser.add_argument("--sem-excel", action="store_true",
                        help="Não gera os .xlsx por regional")
    parser.add_argument("--data-ref", default=None,
                        help="Força a dt_referencia (DD/MM/AAAA ou AAAA-MM-DD)")
    args = parser.parse_args()

    log("═" * 60)
    log("PAINEL DE ALERTAS — TURMAS")
    log("═" * 60)

    dt_ref, origem = resolver_data_referencia(args.data_ref)
    log(f"dt_referencia = {dt_ref:%d/%m/%Y}  (origem: {origem})")

    excel_dir = EXCEL_BASE / datetime.now().strftime("%d_%m_%Y")   # ex.: 15_10_2026

    historico = carregar_historico(RESUMO_PATH)
    df_base = carregar_base()

    novos = []            # frames de resumo gerados nesta execução
    scripts_novos = set()

    for modulo in VALIDACOES:
        nome = modulo.NOME
        sid = _script_id(modulo)
        saida = RESULTADOS / modulo.ARQUIVO_SAIDA
        log(f"\n▶ Validação: {nome}")

        if ja_processado(historico, sid, dt_ref) and not args.force:
            log(f"  Já existe no histórico ({sid} @ {dt_ref:%d/%m/%Y}). Use --force para regenerar.")
            continue

        try:
            df_resultado = modulo.run(df_base)
            # Arquivo da validação = foto da base mais recente lida (com dt_referencia)
            df_resultado.with_columns(pl.lit(dt_ref).cast(pl.Date).alias(DT_COL)).write_parquet(saida)
            log(f"  ✔ {len(df_resultado):,} registros → {saida.name}")

            frame = (
                df_resultado.select(pl.col(modulo.COLUNAS_RESUMO))
                .with_columns(pl.lit(dt_ref).cast(pl.Date).alias(DT_COL))
            )
            novos.append(_harmonizar(frame))
            scripts_novos.add(sid)

            if not args.sem_excel and hasattr(modulo, "exportar_excel"):
                modulo.exportar_excel(df_resultado, df_base, excel_dir)
        except Exception as e:
            log(f"  ✘ ERRO em {nome}: {e}")
            raise

    # ── Totais (denominadores do app) ─────────────────────────────────────────
    totais = {}
    for modulo in VALIDACOES:
        if hasattr(modulo, "totais"):
            totais.update(modulo.totais(df_base))
    if totais:
        # totais.parquet: mesmo formato de antes (1 linha, sem dt_referencia) -> não quebra o app
        pl.DataFrame([totais]).write_parquet(TOTAIS_PATH)
        # totais_historico.parquet: empilhado por dt_referencia (regrava só a data atual)
        linha = pl.DataFrame([{DT_COL: dt_ref, **totais}]).with_columns(pl.col(DT_COL).cast(pl.Date))
        th = carregar_historico(TOTAIS_HIST_PATH)
        if th is not None:
            th = th.filter(~(pl.col(DT_COL) == dt_ref).fill_null(False))
            linha = _concat([th, linha])
        _gravar_atomico(linha.sort(DT_COL), TOTAIS_HIST_PATH)
        log(f"\n✔ totais.parquet salvo: {totais}")
        log(f"✔ totais_historico.parquet atualizado ({dt_ref:%d/%m/%Y})")

    # ── Consolida resumo (empilhado) ──────────────────────────────────────────
    if novos:
        partes = []
        if historico is not None:
            # remove só o que será substituído: mesma data + mesmas validações reprocessadas
            mascara = (
                (pl.col(DT_COL) == dt_ref) & pl.col("script").is_in(list(scripts_novos))
            ).fill_null(False)
            partes.append(_harmonizar(historico.filter(~mascara)))
        partes.extend(novos)

        resumo = _concat(partes)
        ordem_cols = [DT_COL] + [c for c in resumo.columns if c != DT_COL]
        resumo = resumo.select(ordem_cols)
        chaves_ordem = [c for c in (DT_COL, "script", "nm_regional", "nm_escola", "id_turma")
                        if c in resumo.columns]
        resumo = resumo.sort(chaves_ordem)
        _gravar_atomico(resumo, RESUMO_PATH)

        n_datas = resumo[DT_COL].n_unique()
        log(f"\n✔ resumo.parquet atualizado: {len(resumo):,} registros "
            f"({n_datas} datas de referência) → {RESUMO_PATH}")
        log(f"  Adicionados/substituídos nesta execução: {sum(len(f) for f in novos):,}")
    elif historico is not None:
        log("\nNada novo a empilhar; resumo.parquet mantido como estava.")
    else:
        log("\n[AVISO] Nenhum alerta gerado.")

    log("\n" + "═" * 60)
    log("Processamento concluído.")


if __name__ == "__main__":
    main()
