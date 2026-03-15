"""
app_streamlit.py  —  Generatore Associazioni Verona (interfaccia web)
─────────────────────────────────────────────────────────────────────
Avvio:
    streamlit run app_streamlit.py

La prima volta imposta il percorso della cartella del progetto
(es. D:\\Associazioni_2026) nella barra laterale.
Il percorso viene salvato in  config.txt  accanto a questo file.
"""

import streamlit as st
import sqlite3
import shutil
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

st.set_page_config(
    page_title="Associazioni Verona",
    page_icon="🏛️",
    layout="centered",
)

# ── Percorso configurazione ───────────────────────────────────────────────────

_HERE = Path(__file__).parent
_CONFIG_FILE = _HERE / "config.txt"


def _leggi_progetto_dir() -> str:
    if _CONFIG_FILE.exists():
        return _CONFIG_FILE.read_text(encoding="utf-8").strip()
    return ""


def _salva_progetto_dir(path: str) -> None:
    _CONFIG_FILE.write_text(path.strip(), encoding="utf-8")


# ── Sidebar: selezione cartella progetto ──────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Configurazione")
    saved = _leggi_progetto_dir()
    progetto_dir = st.text_input(
        "Percorso cartella progetto",
        value=saved,
        placeholder=r"es. D:\Associazioni_2026",
        help="Cartella che contiene main.tex, AssociazioneModelloVuoto.tex e associazioni.db",
    )
    if st.button("💾 Salva percorso"):
        _salva_progetto_dir(progetto_dir)
        st.success("Percorso salvato!")

    if progetto_dir and Path(progetto_dir).is_dir():
        st.success(f"✅ Cartella trovata")
    elif progetto_dir:
        st.error("❌ Cartella non trovata")

PROJECT = Path(progetto_dir) if progetto_dir else None

TEMPLATE_PATH   = PROJECT / "AssociazioneModelloVuoto.tex" if PROJECT else None
DB_PATH         = PROJECT / "associazioni.db"              if PROJECT else None
MAIN_TEX_PATH   = PROJECT / "main.tex"                     if PROJECT else None
INDICE_TEX_PATH = PROJECT / "indice.tex"                   if PROJECT else None
ARCHIVIO_DIR    = PROJECT / "archivio"                     if PROJECT else None


# ── Utilità ───────────────────────────────────────────────────────────────────

def sanitize_nome(nome: str) -> str:
    nfkd      = unicodedata.normalize("NFKD", nome)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    safe      = re.sub(r"[^\w\s-]", "", ascii_str)
    safe      = re.sub(r"\s+", "_", safe).strip("_")
    return safe or "Associazione"


_LATEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&":  r"\&",
    "%":  r"\%",
    "$":  r"\$",
    "#":  r"\#",
    "_":  r"\_",
    "{":  r"\{",
    "}":  r"\}",
    "~":  r"\textasciitilde{}",
    "^":  r"\textasciicircum{}",
}
_LATEX_PATTERN = re.compile("|".join(re.escape(k) for k in _LATEX_SPECIAL))


def escape_latex(text: str) -> str:
    return _LATEX_PATTERN.sub(lambda m: _LATEX_SPECIAL[m.group()], text)


# ── DB ────────────────────────────────────────────────────────────────────────

def _init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS associazioni (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                nome             TEXT,
                ambito           TEXT,
                didascalia       TEXT,
                chi_siamo        TEXT,
                attivita1        TEXT,
                attivita2        TEXT,
                attivita3        TEXT,
                attivita4        TEXT,
                progetti         TEXT,
                indirizzo        TEXT,
                tel              TEXT,
                email            TEXT,
                data_inserimento TEXT
            )
        """)


def _leggi_associazioni() -> list:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT id, nome, ambito, data_inserimento FROM associazioni ORDER BY nome COLLATE NOCASE"
        ).fetchall()


def _elimina_record(record_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM associazioni WHERE id = ?", (record_id,))


# ── main.tex / indice.tex ─────────────────────────────────────────────────────

def aggiorna_main_tex(nome_cartella: str, tex_no_ext: str) -> bool:
    if not MAIN_TEX_PATH.exists():
        return False
    nuova_riga = f"\\input{{archivio/{nome_cartella}/{tex_no_ext}}}"
    lines = MAIN_TEX_PATH.read_text(encoding="utf-8").splitlines(keepends=True)

    start_idx = end_idx = None
    for i, line in enumerate(lines):
        if start_idx is None and "% ASSOCIAZIONI" in line:
            start_idx = i + 1
        elif start_idx is not None and r"\cleardoublepage" in line:
            end_idx = i
            break
    if start_idx is None:
        for i, line in enumerate(lines):
            if r"\cleardoublepage" in line:
                start_idx = end_idx = i
                break
    if end_idx is None:
        for i, line in enumerate(lines):
            if r"\end{document}" in line:
                end_idx   = i
                start_idx = start_idx if start_idx is not None else i
                break
    if end_idx is None:
        end_idx   = len(lines)
        start_idx = start_idx or end_idx

    sezione     = lines[start_idx:end_idx]
    righe_input = [l.strip() for l in sezione if l.strip().startswith(r"\input{")]
    if nuova_riga not in righe_input:
        righe_input.append(nuova_riga)

    def _key(r):
        m = re.match(r"\\input\{archivio/([^/]+)/", r)
        return m.group(1).lower().replace("_", " ") if m else r.lower()

    righe_input.sort(key=_key)
    nuova_sezione = ["\n"] + [r + "\n" for r in righe_input] + ["\n"]
    MAIN_TEX_PATH.write_text(
        "".join(lines[:start_idx] + nuova_sezione + lines[end_idx:]),
        encoding="utf-8",
    )
    return True


def rimuovi_da_main_tex(nome_cartella: str) -> None:
    if not MAIN_TEX_PATH.exists():
        return
    lines = MAIN_TEX_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    nuove = [l for l in lines
             if not (l.strip().startswith(r"\input{") and f"archivio/{nome_cartella}/" in l)]
    if nuove != lines:
        MAIN_TEX_PATH.write_text("".join(nuove), encoding="utf-8")


def aggiorna_indice_tex() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        nomi = [r[0] for r in conn.execute(
            "SELECT nome FROM associazioni ORDER BY nome COLLATE NOCASE"
        )]
    if not nomi:
        return
    righe = [
        "% INDICE AUTOGENERATO — NON MODIFICARE MANUALMENTE\n",
        "\\section*{Indice delle Associazioni}\n",
        "\\begin{multicols}{2}\n",
        "\\setlength{\\columnsep}{1.5em}\n",
        "\\begin{itemize}[label={},leftmargin=0pt,itemsep=3pt,topsep=0pt]\n",
    ]
    for nome in nomi:
        label = f"assoc:{sanitize_nome(nome)}"
        righe.append(f"\\item {escape_latex(nome)}\\dotfill\\pageref{{{label}}}\n")
    righe += ["\\end{itemize}\n", "\\end{multicols}\n"]
    INDICE_TEX_PATH.write_text("".join(righe), encoding="utf-8")

    # Assicura \usepackage{multicol} e \input{indice} in main.tex
    if not MAIN_TEX_PATH.exists():
        return
    testo = MAIN_TEX_PATH.read_text(encoding="utf-8")
    mod   = False
    if "\\usepackage{multicol}" not in testo:
        anchor = "\\usepackage{caption}" if "\\usepackage{caption}" in testo else "\\begin{document}"
        testo  = testo.replace(anchor, "\\usepackage{multicol}\n" + anchor)
        mod    = True
    if "\\input{indice}" not in testo:
        pos = testo.find("% INDICE EVENTUALE")
        if pos != -1:
            pos_c = testo.find(r"\cleardoublepage", pos)
            ins   = testo.find("\n", pos_c) + 1 if pos_c != -1 else testo.find("\n", pos) + 1
            testo = testo[:ins] + "\\input{indice}\n" + testo[ins:]
        else:
            testo = testo.replace("\\end{document}", "\\cleardoublepage\n\\input{indice}\n\\end{document}")
        mod = True
    if mod:
        MAIN_TEX_PATH.write_text(testo, encoding="utf-8")


# ── Genera .tex ───────────────────────────────────────────────────────────────

def genera_tex(data: dict, logo_bytes, logo_ext, foto_bytes, foto_ext) -> tuple[bool, str]:
    """Crea la cartella, copia immagini, scrive il .tex. Restituisce (ok, messaggio)."""

    # Salva in DB
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if conn.execute(
                "SELECT id FROM associazioni WHERE nome = ?", (data["nome"],)
            ).fetchone():
                return False, f"⚠️ «{data['nome']}» è già presente nel database."
            cur = conn.execute("""
                INSERT INTO associazioni
                    (nome,ambito,didascalia,chi_siamo,
                     attivita1,attivita2,attivita3,attivita4,
                     progetti,indirizzo,tel,email,data_inserimento)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, tuple(data[k] for k in [
                "nome","ambito","didascalia","chi_siamo",
                "attivita1","attivita2","attivita3","attivita4",
                "progetti","indirizzo","tel","email","data_inserimento",
            ]))
    except sqlite3.Error as e:
        return False, f"Errore DB: {e}"

    # Crea cartella
    nome_safe  = sanitize_nome(data["nome"])
    output_dir = ARCHIVIO_DIR / nome_safe
    output_dir.mkdir(parents=True, exist_ok=True)

    # Salva immagini
    logo_dest = foto_dest = None
    if logo_bytes:
        logo_dest = output_dir / f"logo{logo_ext}"
        logo_dest.write_bytes(logo_bytes)
    if foto_bytes:
        foto_dest = output_dir / f"foto{foto_ext}"
        foto_dest.write_bytes(foto_bytes)

    # Legge template
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError as e:
        return False, f"Impossibile leggere il template: {e}"

    # Pulizia eventuale codice Python residuo nel template
    template = re.sub(
        r"# Genera item[^\n]*\n(.*?\n)*?.*?(?:IF_ATTV_ITEMS|att_block)[^\n]*\n",
        "", template, flags=re.DOTALL,
    )
    template = template.replace("IF_CONTATTI", "")

    # Costruisce blocco attività
    def _att(testo, punt):
        return (r"\item " + escape_latex(testo) + punt) if testo.strip() else ""

    att_voci = [v for v in [
        _att(data["attivita1"], ";"),
        _att(data["attivita2"], ";"),
        _att(data["attivita3"], ";"),
        _att(data["attivita4"], "."),
    ] if v]

    if att_voci:
        att_block = (
            "\\subsection*{Cosa facciamo}\n\n"
            "\\begin{itemize}[label=--]\n"
            + "\n".join(att_voci)
            + "\n\\end{itemize}"
        )
    else:
        att_block = ""

    # Sostituzioni
    sost = {
        "NOME ASSOCIAZIONE \u2013 Ambito":
            f"{escape_latex(data['nome'])} \u2013 {escape_latex(data['ambito'])}",
        "assoc:NOME_SAFE":   f"assoc:{nome_safe}",
        "Breve didascalia":  escape_latex(data["didascalia"]),
        "Testo descrittivo sintetico.  \nMassimo 12\u201315 righe per mantenere equilibrio visivo.":
            data["chi_siamo"],
        "\\subsection*{Cosa facciamo}\n\n\\begin{itemize}[label=--]\n"
        "\\item Punto attivit\u00e0 uno;\n"
        "\\item Punto attivit\u00e0 due;\n"
        "\\item Punto attivit\u00e0 tre;\n"
        "\\item Punto attivit\u00e0 quattro.\n"
        "\\end{itemize}": att_block,
        r"\item Punto attività uno;":    _att(data["attivita1"], ";"),
        r"\item Punto attività due;":    _att(data["attivita2"], ";"),
        r"\item Punto attività tre;":    _att(data["attivita3"], ";"),
        r"\item Punto attività quattro.": _att(data["attivita4"], "."),
        "Breve frase conclusiva che chiude la prima pagina.": "",
        "Testo di approfondimento.  \nQui puoi sviluppare meglio missione, collaborazioni, storia, impatto sul territorio.\n\nAltri 2\u20133 paragrafi equilibrati.":
            data["progetti"],
        "NOME ASSOCIAZIONE": escape_latex(data["nome"]),
        "Indirizzo completo": escape_latex(data["indirizzo"]) if data["indirizzo"] else "",
        "Tel: xxx xxx xxxx":  (f"Tel: {escape_latex(data['tel'])}") if data["tel"] else "",
        "email@associazione.it":
            (r"\texttt{" + escape_latex(data["email"]) + "}") if data["email"] else "",
    }
    for old, new in sost.items():
        template = template.replace(old, new)

    # Rimuove itemize vuoto residuo
    template = re.sub(
        r"\\subsection\*\{Cosa facciamo\}\s*\n\\begin\{itemize\}\[label=--\]\s*\n\s*\\end\{itemize\}",
        "", template,
    )
    template = re.sub(r"\n{3,}", "\n\n", template)

    # Immagini
    if logo_dest:
        template = template.replace("percorso/logo.jpg", f"archivio/{nome_safe}/logo{logo_ext}")
    else:
        template = re.sub(
            r"\\noindent\s*\n\\begin\{minipage\}.*?\\end\{minipage\}\s*\n",
            "", template, flags=re.DOTALL,
        )
    if foto_dest:
        template = template.replace("percorso/foto.jpg", f"archivio/{nome_safe}/foto{foto_ext}")
    else:
        template = re.sub(
            r"\\begin\{wrapfigure\}.*?\\end\{wrapfigure\}\s*\n",
            "", template, flags=re.DOTALL,
        )

    # Scrive .tex
    tex_filename = f"Associazione_{nome_safe}.tex"
    (output_dir / tex_filename).write_text(template, encoding="utf-8")

    # Aggiorna main.tex e indice.tex
    aggiorna_main_tex(nome_safe, tex_filename.replace(".tex", ""))
    aggiorna_indice_tex()

    img_log = []
    if logo_dest: img_log.append(f"logo{logo_ext}")
    if foto_dest: img_log.append(f"foto{foto_ext}")

    msg = (
        f"✅ **{data['nome']}** salvata con successo!\n\n"
        f"- Cartella: `archivio/{nome_safe}/`\n"
        f"- File .tex: `{tex_filename}`\n"
    )
    if img_log:
        msg += f"- Immagini: {', '.join(img_log)}\n"
    msg += "- `main.tex` e `indice.tex` aggiornati"
    return True, msg


# ══════════════════════════════════════════════════════════════════════════════
# UI principale
# ══════════════════════════════════════════════════════════════════════════════

st.title("🏛️ Associazioni di Verona — Centro Storico")

if not PROJECT or not PROJECT.is_dir():
    st.warning("👈 Imposta il percorso della cartella progetto nella barra laterale.")
    st.stop()

if not TEMPLATE_PATH.exists():
    st.error(f"Template non trovato: `{TEMPLATE_PATH}`\nAssicurati che `AssociazioneModelloVuoto.tex` sia nella cartella del progetto.")
    st.stop()

_init_db()

tab_nuovo, tab_lista = st.tabs(["➕ Nuova Associazione", "📋 Elenco e Gestione"])

# ── TAB 1: Inserimento ────────────────────────────────────────────────────────
with tab_nuovo:
    st.subheader("Dati dell'associazione")

    col1, col2 = st.columns(2)
    with col1:
        nome    = st.text_input("Nome Associazione *", placeholder="es. Associazione Amici del Verde")
    with col2:
        ambito  = st.text_input("Ambito", placeholder="es. Ambiente, Cultura, Sport…")

    chi_siamo = st.text_area(
        "Chi siamo",
        placeholder="Testo descrittivo sintetico (max 12–15 righe per mantenere equilibrio visivo)",
        height=180,
    )

    st.subheader("Attività principali")
    st.caption("Lascia vuoti i campi delle attività non utilizzate — verranno omessi automaticamente.")
    att1 = st.text_input("Attività 1", placeholder="Prima attività principale")
    att2 = st.text_input("Attività 2", placeholder="Seconda attività principale")
    att3 = st.text_input("Attività 3", placeholder="Terza attività principale")
    att4 = st.text_input("Attività 4", placeholder="Quarta attività principale")

    st.subheader("Progetti e iniziative")
    progetti = st.text_area(
        "Progetti",
        placeholder="Testo di approfondimento su progetti o iniziative (pagina 2)",
        height=150,
    )

    st.subheader("Contatti")
    col3, col4, col5 = st.columns(3)
    with col3:
        indirizzo = st.text_input("Indirizzo", placeholder="Via Roma 1, 37121 Verona")
    with col4:
        tel       = st.text_input("Telefono", placeholder="045 123456")
    with col5:
        email     = st.text_input("Email", placeholder="info@associazione.it")

    st.subheader("Immagini")
    st.caption("Formati accettati: jpg, jpeg, png, pdf")
    col6, col7 = st.columns(2)
    with col6:
        logo_file = st.file_uploader("Logo", type=["jpg","jpeg","png","pdf"], key="logo")
    with col7:
        foto_file = st.file_uploader("Foto", type=["jpg","jpeg","png","pdf"], key="foto")

    didascalia = st.text_input(
        "Didascalia foto",
        placeholder="Breve didascalia della foto (max 1 riga)",
        disabled=(foto_file is None),
    )

    st.divider()

    if st.button("💾 Salva e Genera", type="primary", use_container_width=True):
        if not nome.strip():
            st.error("Il campo **Nome Associazione** è obbligatorio.")
        else:
            logo_bytes = logo_file.read() if logo_file else None
            logo_ext   = Path(logo_file.name).suffix.lower() if logo_file else None
            foto_bytes = foto_file.read() if foto_file else None
            foto_ext   = Path(foto_file.name).suffix.lower() if foto_file else None

            data = {
                "nome":             nome.strip(),
                "ambito":           ambito.strip(),
                "didascalia":       didascalia.strip(),
                "chi_siamo":        chi_siamo.strip(),
                "attivita1":        att1.strip(),
                "attivita2":        att2.strip(),
                "attivita3":        att3.strip(),
                "attivita4":        att4.strip(),
                "progetti":         progetti.strip(),
                "indirizzo":        indirizzo.strip(),
                "tel":              tel.strip(),
                "email":            email.strip(),
                "data_inserimento": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

            ok, msg = genera_tex(data, logo_bytes, logo_ext, foto_bytes, foto_ext)
            if ok:
                st.success(msg)
                st.balloons()
            else:
                st.error(msg)

# ── TAB 2: Elenco e Gestione ──────────────────────────────────────────────────
with tab_lista:
    st.subheader("Associazioni nel database")

    records = _leggi_associazioni()

    if not records:
        st.info("Nessuna associazione inserita ancora.")
    else:
        st.caption(f"{len(records)} associazioni presenti")
        for rec_id, rec_nome, rec_ambito, rec_data in records:
            with st.expander(f"**{rec_nome}** — {rec_ambito or '—'}  ·  {rec_data or ''}"):
                st.write(f"ID database: `{rec_id}`")
                nome_safe = sanitize_nome(rec_nome)
                cartella  = ARCHIVIO_DIR / nome_safe
                if cartella.is_dir():
                    files = list(cartella.iterdir())
                    st.write("File in archivio: " + ", ".join(f"`{f.name}`" for f in files))
                else:
                    st.warning("Cartella in archivio non trovata.")

                col_a, col_b = st.columns([1, 3])
                with col_a:
                    if st.button("🗑️ Elimina", key=f"del_{rec_id}"):
                        st.session_state[f"confirm_{rec_id}"] = True

                if st.session_state.get(f"confirm_{rec_id}"):
                    st.warning(f"Confermi l'eliminazione di **{rec_nome}**?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Sì, elimina", key=f"yes_{rec_id}"):
                            _elimina_record(rec_id)
                            if cartella.is_dir():
                                shutil.rmtree(cartella)
                            rimuovi_da_main_tex(nome_safe)
                            aggiorna_indice_tex()
                            st.session_state.pop(f"confirm_{rec_id}", None)
                            st.success(f"«{rec_nome}» eliminata.")
                            st.rerun()
                    with c2:
                        if st.button("❌ Annulla", key=f"no_{rec_id}"):
                            st.session_state.pop(f"confirm_{rec_id}", None)
                            st.rerun()
