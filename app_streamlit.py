
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
st.caption("Compila il modulo e scarica lo zip da inviare al responsabile.")

st.subheader("Dati dell'associazione")

col1, col2 = st.columns(2)
with col1:
    nome   = st.text_input("Nome Associazione *", placeholder="es. Associazione Amici del Verde")
with col2:
    ambito = st.text_input("Ambito", placeholder="es. Ambiente, Cultura, Sport…")

chi_siamo = st.text_area(
    "Chi siamo",
    placeholder="Testo descrittivo sintetico (max 12–15 righe)",
    height=180,
)

st.subheader("Attività principali")
st.caption("Lascia vuoti i campi non utilizzati — verranno omessi automaticamente.")
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
    tel       = st.text_input("Telefono",  placeholder="045 123456")
with col5:
    email     = st.text_input("Email",     placeholder="info@associazione.it")

st.subheader("Immagini")
st.caption("Formati accettati: jpg, jpeg, png, pdf")
col6, col7 = st.columns(2)
with col6:
    logo_file = st.file_uploader("Logo",  type=["jpg","jpeg","png","pdf"], key="logo")
with col7:
    foto_file = st.file_uploader("Foto",  type=["jpg","jpeg","png","pdf"], key="foto")

didascalia = st.text_input(
    "Didascalia foto",
    placeholder="Breve didascalia della foto (max 1 riga)",
    disabled=(foto_file is None),
)

st.divider()

if st.button("📦 Genera ZIP", type="primary", use_container_width=True):
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

        with st.spinner("Generazione in corso…"):
            zip_bytes = crea_zip(data, logo_bytes, logo_ext, foto_bytes, foto_ext)

        nome_safe = sanitize_nome(nome.strip())
        st.success(f"✅ ZIP generato per **{nome.strip()}**")
        st.download_button(
            label="⬇️ Scarica ZIP",
            data=zip_bytes,
            file_name=f"Associazione_{nome_safe}.zip",
            mime="application/zip",
            use_container_width=True,
        )
        st.info(
            "📧 Scarica lo zip e mandalo per email al responsabile.\n\n"
            "Dentro trovi anche il file **ISTRUZIONI.txt** con i passi da seguire."
        )

st.divider()
with st.expander("ℹ️ Come funziona"):
    st.markdown("""
1. **Compila** tutti i campi (solo il Nome è obbligatorio)
2. **Carica** logo e foto se disponibili
3. Clicca **Genera ZIP** e poi **Scarica ZIP**
4. **Manda lo zip** per email al responsabile del progetto
5. Il responsabile lo decomprime nella cartella del progetto e compila il PDF

I campi lasciati vuoti vengono omessi automaticamente nel documento finale.
    """)
