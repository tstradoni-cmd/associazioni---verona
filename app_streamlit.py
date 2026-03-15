"""
app_streamlit.py  —  Generatore Associazioni Verona  (versione cloud)
─────────────────────────────────────────────────────────────────────
Deploy su Streamlit Community Cloud.
La terza persona compila il modulo nel browser e scarica uno zip.
Tu decomprimi lo zip nella cartella del progetto e compili con xelatex.

Struttura zip scaricato:
    archivio/<NomeAssociazione>/
        Associazione_<NomeAssociazione>.tex
        logo.<ext>          (se caricato)
        foto.<ext>          (se caricato)
    _aggiorna_main.txt      (riga input da aggiungere a mano o con script)
"""

import streamlit as st
import sqlite3
import io
import os
import re
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

st.set_page_config(
    page_title="Associazioni Verona",
    page_icon="🏛️",
    layout="centered",
)

# ── Template LaTeX incorporato ────────────────────────────────────────────────
# Il template è scritto direttamente nel codice così non serve un file esterno.

TEMPLATE = r"""\newpage
\label{assoc:NOME_SAFE}

% ======================
% PAGINA 1
% ======================

% --- LOGO ---
\noindent
\begin{minipage}{0.22\textwidth}
    \includegraphics[width=\linewidth]{percorso/logo.jpg}
\end{minipage}

\vspace{0.3cm}

\associazionetitolo{NOME ASSOCIAZIONE – Ambito}

% --- FOTO CON TESTO ATTORNO ---
\begin{wrapfigure}{r}{0.48\textwidth}
    \vspace{-0.5cm}
    \centering
    \includegraphics[width=0.46\textwidth]{percorso/foto.jpg}
    \caption*{\footnotesize\textit{Breve didascalia}}
    \vspace{-0.5cm}
\end{wrapfigure}

\subsection*{Chi siamo}

Testo descrittivo sintetico.  
Massimo 12–15 righe per mantenere equilibrio visivo.

\subsection*{Cosa facciamo}

\begin{itemize}[label=--]
\item Punto attività uno;
\item Punto attività due;
\item Punto attività tre;
\item Punto attività quattro.
\end{itemize}

\clearpage


% ======================
% PAGINA 2
% ======================

\subsection*{Progetti e iniziative}

Testo di approfondimento.  
Qui puoi sviluppare meglio missione, collaborazioni, storia, impatto sul territorio.

Altri 2–3 paragrafi equilibrati.

\vfill
\hrule
\vspace{0.6cm}

\begin{center}
\Large\bfseries NOME ASSOCIAZIONE

\vspace{0.4cm}

Indirizzo completo  

Tel: xxx xxx xxxx  

\texttt{email@associazione.it}
\end{center}
"""


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


# ── Generazione .tex in memoria ───────────────────────────────────────────────

def genera_tex_in_memoria(data: dict, logo_bytes, logo_ext, foto_bytes, foto_ext) -> tuple[str, str]:
    """
    Genera il contenuto del file .tex a partire dai dati e dal template.
    Restituisce (testo_tex, nome_safe).
    """
    nome_safe = sanitize_nome(data["nome"])
    template  = TEMPLATE

    # Blocco attività
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
        "assoc:NOME_SAFE":    f"assoc:{nome_safe}",
        "Breve didascalia":   escape_latex(data["didascalia"]),
        "Testo descrittivo sintetico.  \nMassimo 12\u201315 righe per mantenere equilibrio visivo.":
            data["chi_siamo"],
        "\\subsection*{Cosa facciamo}\n\n\\begin{itemize}[label=--]\n"
        "\\item Punto attivit\u00e0 uno;\n"
        "\\item Punto attivit\u00e0 due;\n"
        "\\item Punto attivit\u00e0 tre;\n"
        "\\item Punto attivit\u00e0 quattro.\n"
        "\\end{itemize}": att_block,
        r"\item Punto attività uno;":     _att(data["attivita1"], ";"),
        r"\item Punto attività due;":     _att(data["attivita2"], ";"),
        r"\item Punto attività tre;":     _att(data["attivita3"], ";"),
        r"\item Punto attività quattro.": _att(data["attivita4"], "."),
        "Breve frase conclusiva che chiude la prima pagina.": "",
        "Testo di approfondimento.  \nQui puoi sviluppare meglio missione, collaborazioni, storia, impatto sul territorio.\n\nAltri 2\u20133 paragrafi equilibrati.":
            data["progetti"],
        "NOME ASSOCIAZIONE":  escape_latex(data["nome"]),
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

    # Immagini
    if logo_bytes:
        template = template.replace("percorso/logo.jpg", f"archivio/{nome_safe}/logo{logo_ext}")
    else:
        template = re.sub(
            r"\\noindent\s*\n\\begin\{minipage\}.*?\\end\{minipage\}\s*\n",
            "", template, flags=re.DOTALL,
        )
    if foto_bytes:
        template = template.replace("percorso/foto.jpg", f"archivio/{nome_safe}/foto{foto_ext}")
    else:
        template = re.sub(
            r"\\begin\{wrapfigure\}.*?\\end\{wrapfigure\}\s*\n",
            "", template, flags=re.DOTALL,
        )

    template = re.sub(r"\n{3,}", "\n\n", template)
    return template, nome_safe


def crea_zip(data: dict, logo_bytes, logo_ext, foto_bytes, foto_ext) -> bytes:
    """Crea lo zip in memoria e restituisce i bytes."""
    tex_content, nome_safe = genera_tex_in_memoria(
        data, logo_bytes, logo_ext, foto_bytes, foto_ext
    )
    tex_filename = f"Associazione_{nome_safe}.tex"
    cartella     = f"archivio/{nome_safe}"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # File .tex
        zf.writestr(f"{cartella}/{tex_filename}", tex_content.encode("utf-8"))

        # Immagini
        if logo_bytes:
            zf.writestr(f"{cartella}/logo{logo_ext}", logo_bytes)
        if foto_bytes:
            zf.writestr(f"{cartella}/foto{foto_ext}", foto_bytes)

        # Istruzioni per il responsabile Linux
        istruzioni = (
            f"ISTRUZIONI PER IL RESPONSABILE\n"
            f"{'='*40}\n\n"
            f"Associazione: {data['nome']}\n"
            f"Data:         {data['data_inserimento']}\n\n"
            f"1. Decomprimi questo zip nella cartella del progetto.\n"
            f"   La struttura archivio/{nome_safe}/ verrà creata automaticamente.\n\n"
            f"2. Aggiungi questa riga a main.tex nel blocco %% ASSOCIAZIONI:\n\n"
            f"   \\input{{archivio/{nome_safe}/{tex_filename.replace('.tex','')}}}\n\n"
            f"3. Esegui due volte: xelatex main\n"
        )
        zf.writestr("ISTRUZIONI.txt", istruzioni.encode("utf-8"))

    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

st.title("🏛️ Associazioni di Verona — Centro Storico")

# ── Session state ─────────────────────────────────────────────────────────────
if "coda" not in st.session_state:
    st.session_state.coda = []   # lista di dict {data, logo_bytes, logo_ext, foto_bytes, foto_ext}
if "form_key" not in st.session_state:
    st.session_state.form_key = 0  # incrementato per resettare i widget


def _aggiungi(data, logo_bytes, logo_ext, foto_bytes, foto_ext):
    st.session_state.coda.append({
        "data": data,
        "logo_bytes": logo_bytes, "logo_ext": logo_ext,
        "foto_bytes": foto_bytes, "foto_ext": foto_ext,
    })
    st.session_state.form_key += 1   # forza reset del form


def _rimuovi(idx):
    st.session_state.coda.pop(idx)


def _crea_zip_multiplo() -> bytes:
    """Crea un unico zip con tutte le associazioni in coda."""
    import io, zipfile
    buf = io.BytesIO()
    istruzioni_righe = [
        "ISTRUZIONI PER IL RESPONSABILE\n",
        "=" * 40 + "\n\n",
        f"Data invio: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"Associazioni incluse: {len(st.session_state.coda)}\n\n",
        "Per ciascuna associazione aggiungi a main.tex nel blocco % ASSOCIAZIONI:\n\n",
    ]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in st.session_state.coda:
            d          = item["data"]
            nome_safe  = sanitize_nome(d["nome"])
            tex, _     = genera_tex_in_memoria(
                d, item["logo_bytes"], item["logo_ext"],
                item["foto_bytes"], item["foto_ext"]
            )
            tex_fname  = f"Associazione_{nome_safe}.tex"
            cartella   = f"archivio/{nome_safe}"

            zf.writestr(f"{cartella}/{tex_fname}", tex.encode("utf-8"))
            if item["logo_bytes"]:
                zf.writestr(f"{cartella}/logo{item['logo_ext']}", item["logo_bytes"])
            if item["foto_bytes"]:
                zf.writestr(f"{cartella}/foto{item['foto_ext']}", item["foto_bytes"])

            istruzioni_righe.append(
                f"  \\input{{archivio/{nome_safe}/{tex_fname.replace('.tex','')}}}\n"
            )

        istruzioni_righe.append("\nDopo aver copiato le righe esegui due volte: xelatex main\n")
        zf.writestr("ISTRUZIONI.txt", "".join(istruzioni_righe).encode("utf-8"))
    return buf.getvalue()


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_form, tab_coda = st.tabs([
    "➕ Inserisci Associazione",
    f"📦 Pronte per invio ({len(st.session_state.coda)})",
])

# ── TAB 1: Modulo inserimento ─────────────────────────────────────────────────
with tab_form:
    k = st.session_state.form_key   # usato come suffix nei key dei widget per forzare reset

    st.subheader("Dati dell'associazione")
    col1, col2 = st.columns(2)
    with col1:
        nome   = st.text_input("Nome Associazione *", placeholder="es. Associazione Amici del Verde", key=f"nome_{k}")
    with col2:
        ambito = st.text_input("Ambito", placeholder="es. Ambiente, Cultura, Sport…", key=f"ambito_{k}")

    chi_siamo = st.text_area("Chi siamo",
        placeholder="Testo descrittivo sintetico (max 12–15 righe)", height=180, key=f"chi_{k}")

    st.subheader("Attività principali")
    st.caption("Lascia vuoti i campi non utilizzati — verranno omessi automaticamente.")
    att1 = st.text_input("Attività 1", placeholder="Prima attività principale",  key=f"a1_{k}")
    att2 = st.text_input("Attività 2", placeholder="Seconda attività principale", key=f"a2_{k}")
    att3 = st.text_input("Attività 3", placeholder="Terza attività principale",   key=f"a3_{k}")
    att4 = st.text_input("Attività 4", placeholder="Quarta attività principale",  key=f"a4_{k}")

    st.subheader("Progetti e iniziative")
    progetti = st.text_area("Progetti",
        placeholder="Testo di approfondimento su progetti o iniziative (pagina 2)",
        height=150, key=f"prog_{k}")

    st.subheader("Contatti")
    col3, col4, col5 = st.columns(3)
    with col3:
        indirizzo = st.text_input("Indirizzo", placeholder="Via Roma 1, 37121 Verona", key=f"ind_{k}")
    with col4:
        tel       = st.text_input("Telefono",  placeholder="045 123456",               key=f"tel_{k}")
    with col5:
        email     = st.text_input("Email",     placeholder="info@associazione.it",      key=f"email_{k}")

    st.subheader("Immagini")
    st.caption("Formati accettati: jpg, jpeg, png, pdf")
    col6, col7 = st.columns(2)
    with col6:
        logo_file = st.file_uploader("Logo", type=["jpg","jpeg","png","pdf"], key=f"logo_{k}")
    with col7:
        foto_file = st.file_uploader("Foto", type=["jpg","jpeg","png","pdf"], key=f"foto_{k}")

    didascalia = st.text_input("Didascalia foto",
        placeholder="Breve didascalia della foto (max 1 riga)",
        disabled=(foto_file is None), key=f"did_{k}")

    st.divider()

    if st.button("✅ Aggiungi alla lista", type="primary", use_container_width=True):
        if not nome.strip():
            st.error("Il campo **Nome Associazione** è obbligatorio.")
        elif any(i["data"]["nome"] == nome.strip() for i in st.session_state.coda):
            st.warning(f"«{nome.strip()}» è già nella lista.")
        else:
            _aggiungi(
                data={
                    "nome": nome.strip(), "ambito": ambito.strip(),
                    "didascalia": didascalia.strip(), "chi_siamo": chi_siamo.strip(),
                    "attivita1": att1.strip(), "attivita2": att2.strip(),
                    "attivita3": att3.strip(), "attivita4": att4.strip(),
                    "progetti": progetti.strip(), "indirizzo": indirizzo.strip(),
                    "tel": tel.strip(), "email": email.strip(),
                    "data_inserimento": datetime.now().strftime("%Y-%m-%d %H:%M"),
                },
                logo_bytes=logo_file.read() if logo_file else None,
                logo_ext=Path(logo_file.name).suffix.lower() if logo_file else None,
                foto_bytes=foto_file.read() if foto_file else None,
                foto_ext=Path(foto_file.name).suffix.lower() if foto_file else None,
            )
            st.success(f"✅ **{nome.strip()}** aggiunta! Ora puoi inserire la prossima.")
            st.rerun()

    with st.expander("ℹ️ Come funziona"):
        st.markdown("""
1. Compila i campi e clicca **Aggiungi alla lista**
2. Il modulo si svuota — inserisci la prossima associazione
3. Quando hai finito vai al tab **Pronte per invio**
4. Clicca **Scarica ZIP** e manda il file per email al responsabile
        """)

# ── TAB 2: Coda e download ────────────────────────────────────────────────────
with tab_coda:
    if not st.session_state.coda:
        st.info("Nessuna associazione ancora inserita. Usa il tab **Inserisci Associazione**.")
    else:
        st.subheader(f"{len(st.session_state.coda)} associazioni pronte")

        for i, item in enumerate(st.session_state.coda):
            d = item["data"]
            col_a, col_b = st.columns([6, 1])
            with col_a:
                imgs = []
                if item["logo_bytes"]: imgs.append("logo")
                if item["foto_bytes"]: imgs.append("foto")
                img_str = f"  ·  📎 {', '.join(imgs)}" if imgs else ""
                st.write(f"**{i+1}. {d['nome']}** — {d['ambito'] or '—'}{img_str}")
            with col_b:
                if st.button("🗑️", key=f"rm_{i}", help="Rimuovi"):
                    _rimuovi(i)
                    st.rerun()

        st.divider()

        with st.spinner("Preparazione ZIP…"):
            zip_data = _crea_zip_multiplo()

        data_str  = datetime.now().strftime("%Y%m%d")
        n         = len(st.session_state.coda)
        zip_fname = f"Associazioni_Verona_{data_str}_{n}voci.zip"

        st.download_button(
            label=f"⬇️ Scarica ZIP ({n} associazioni)",
            data=zip_data,
            file_name=zip_fname,
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )
        st.info("Dopo aver scaricato lo zip, mandalo per email al responsabile.")

        if st.button("🗑️ Svuota lista", use_container_width=True):
            st.session_state.coda = []
            st.session_state.form_key += 1
            st.rerun()
