#!/usr/bin/env python3
import streamlit as st
import pandas as pd
import json
import base64
import io
from datetime import datetime

try:
    import qrcode
    from PIL import Image
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from pyzbar.pyzbar import decode
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False


try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

FOLDER_ID = "1ZVocu_kAXc_fFxCi_0ntwN06VyGYQn9P"
FILENAME  = "FGas_Dati.json"

st.set_page_config(page_title="FGas Registro", page_icon="🔧", layout="wide", initial_sidebar_state="expanded")

# ==================== FUNZIONI GOOGLE DRIVE ====================
def get_drive_service():
    if not GOOGLE_AVAILABLE:
        st.sidebar.warning("Librerie Google non installate.")
        return None
    try:
        if "gcp_service_account" in st.secrets:
            credentials = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=["https://www.googleapis.com/auth/drive"]
            )
            return build("drive", "v3", credentials=credentials)
        else:
            st.sidebar.warning('Secret "gcp_service_account" non trovato.')
    except Exception as e:
        st.sidebar.error(f"Errore connessione Drive: {e}")
    return None

def trova_file_drive(service, nome):
    query = f"name = '{nome}' and trashed = false"
    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name, modifiedTime)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = results.get("files", [])
    return files[0] if files else None

def carica_dati_drive():
    service = get_drive_service()
    if not service:
        return None
    try:
        file_info = trova_file_drive(service, FILENAME)
        if file_info:
            request = service.files().get_media(fileId=file_info["id"])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.seek(0)
            dati = json.load(fh)
            st.sidebar.success(f"Dati caricati da Drive ({file_info['modifiedTime'][:10]})")
            return dati
        else:
            st.sidebar.info(f"File '{FILENAME}' non trovato su Drive. Verranno usati i dati locali.")
    except Exception as e:
        st.sidebar.error(f"Errore caricamento Drive: {e}")
    return None

def salva_dati_drive(dati, silent=False):
    service = get_drive_service()
    if not service:
        if not silent:
            st.toast("Drive non configurato", icon="⚠️")
        return False
    try:
        file_info = trova_file_drive(service, FILENAME)
        payload = json.dumps(dati, indent=2, ensure_ascii=False).encode("utf-8")
        media = MediaIoBaseUpload(io.BytesIO(payload), mimetype="application/json", resumable=True)
        if file_info:
            service.files().update(
                fileId=file_info["id"],
                media_body=media,
                supportsAllDrives=True
            ).execute()
            if not silent:
                st.toast("Salvato su Google Drive", icon="✅")
            return True
        else:
            if not silent:
                st.error(f"File '{FILENAME}' non trovato su Drive.")
                st.info("Crea manualmente il file FGas_Dati.json nel tuo Google Drive, condividilo come Editor con il service account, poi riprova.")
            return False
    except Exception as e:
        if not silent:
            st.error(f"Errore salvataggio Drive: {e}")
        return False


# ==================== GESTIONE SESSIONE MULTI-ACCESSO ====================
def get_sessione_attiva_drive():
    """Legge se c'e una sessione attiva recente (< 2 ore)."""
    # 1) Prova prima dai dati in memoria (piu veloce)
    if "data" in st.session_state and "sessione_attiva" in st.session_state.data:
        sessione = st.session_state.data["sessione_attiva"]
        ts = sessione.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            if (datetime.now() - dt).total_seconds() < 7200:  # 2 ore
                return sessione
        except Exception:
            pass
    # 2) Fallback: leggi da Drive
    service = get_drive_service()
    if not service:
        return None
    try:
        file_info = trova_file_drive(service, FILENAME)
        if file_info:
            request = service.files().get_media(fileId=file_info["id"])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.seek(0)
            dati = json.load(fh)
            sessione = dati.get("sessione_attiva")
            if sessione:
                ts = sessione.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts)
                    if (datetime.now() - dt).total_seconds() < 7200:
                        return sessione
                except Exception:
                    pass
    except Exception:
        pass
    return None


def set_sessione_attiva_drive(tecnico):
    """Scrive su Drive chi e loggato."""
    if "data" not in st.session_state:
        return
    st.session_state.data["sessione_attiva"] = {
        "tecnico": tecnico,
        "timestamp": datetime.now().isoformat()
    }
    salva_dati_drive(st.session_state.data, silent=True)

def clear_sessione_attiva_drive():
    """Rimuove la sessione attiva da Drive."""
    if "data" not in st.session_state:
        return
    if "sessione_attiva" in st.session_state.data:
        del st.session_state.data["sessione_attiva"]
        salva_dati_drive(st.session_state.data, silent=True)


DEFAULT_DATA = {
    "config": {
        "colori_gas": {
            "R32": "#C62828",
            "R410": "#F06292",
            "R407": "#795548",
            "R424": "#7B1FA2",
            "Misto": "#9E9E9E"
        },
        "ultimo_id_bombola": 260,
        "url_base_app": ""
    },
    "tecnici": [
        {
            "nome": "Pierluigi",
            "patentino": "",
            "scadenza": ""
        },
        {
            "nome": "Yarema",
            "patentino": "",
            "scadenza": ""
        },
        {
            "nome": "Gioele",
            "patentino": "",
            "scadenza": ""
        },
        {
            "nome": "Terry",
            "patentino": "",
            "scadenza": ""
        },
        {
            "nome": "Christian",
            "patentino": "",
            "scadenza": ""
        },
        {
            "nome": "Manuel",
            "patentino": "",
            "scadenza": ""
        }
    ],
    "bombole": [
        {
            "tipo_gas": "R410",
            "id_interno": "250",
            "qta_presente": 3.98,
            "seriale": "S5301225",
            "tipo_bombola": "Cariche",
            "tara": 7.94,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R410",
            "id_interno": "253",
            "qta_presente": 6.07,
            "seriale": "S5304230",
            "tipo_bombola": "Cariche",
            "tara": 8.15,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R410",
            "id_interno": "248",
            "qta_presente": 0.0,
            "seriale": "S5328598",
            "tipo_bombola": "Cariche",
            "tara": 7.94,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "RESTITUITA",
            "note": "Restituita 02-07-2026"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "254",
            "qta_presente": 10.12,
            "seriale": "S5321029",
            "tipo_bombola": "Cariche",
            "tara": 7.98,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R407",
            "id_interno": "170",
            "qta_presente": 0.0,
            "seriale": "S5226387",
            "tipo_bombola": "Cariche",
            "tara": 7.59,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "RESTITUITA",
            "note": "Restituita 03-07-2026"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "251",
            "qta_presente": 4.7,
            "seriale": "S5326005",
            "tipo_bombola": "Cariche",
            "tara": 7.98,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R407",
            "id_interno": "171",
            "qta_presente": 5.74,
            "seriale": "S52369772",
            "tipo_bombola": "Cariche",
            "tara": 7.61,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "Christian",
            "data_assegnazione": "09-07-2026",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": "09-07-2026 – Presa da CHRISTIAN"
        },
        {
            "tipo_gas": "R407",
            "id_interno": "173",
            "qta_presente": 2.1,
            "seriale": "S5184095",
            "tipo_bombola": "Cariche",
            "tara": 7.6,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R407",
            "id_interno": "255",
            "qta_presente": 11.23,
            "seriale": "S5302011",
            "tipo_bombola": "Cariche",
            "tara": 8.07,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "247",
            "qta_presente": 4.995,
            "seriale": "F0298282",
            "tipo_bombola": "Cariche",
            "tara": 7.87,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "200",
            "qta_presente": 0.0,
            "seriale": "28179",
            "tipo_bombola": "Cariche",
            "tara": 7.92,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "PROPRIA",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "202",
            "qta_presente": 0.09,
            "seriale": "27967",
            "tipo_bombola": "Cariche",
            "tara": 7.89,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "199",
            "qta_presente": 0.08,
            "seriale": "30009",
            "tipo_bombola": "Cariche",
            "tara": 7.98,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "194",
            "qta_presente": 0.02,
            "seriale": "73339",
            "tipo_bombola": "Cariche",
            "tara": 6.05,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "R32-2",
            "qta_presente": 0.0,
            "seriale": "147401",
            "tipo_bombola": "Recupero",
            "tara": 6.03,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "Recupero"
        },
        {
            "tipo_gas": "R32",
            "id_interno": "R32-1",
            "qta_presente": 0.0,
            "seriale": "147402",
            "tipo_bombola": "Recupero",
            "tara": 6.08,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "Recupero"
        },
        {
            "tipo_gas": "R32",
            "id_interno": "R32-3",
            "qta_presente": 0.0,
            "seriale": "119195",
            "tipo_bombola": "Recupero",
            "tara": 6.08,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "Recupero"
        },
        {
            "tipo_gas": "R32",
            "id_interno": "203",
            "qta_presente": 0.0,
            "seriale": "28647",
            "tipo_bombola": "Cariche",
            "tara": 7.9,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "ATTENZIONE – RECUPERATO R410 IN QUESTA!"
        },
        {
            "tipo_gas": "Misto",
            "id_interno": "179",
            "qta_presente": 0.0,
            "seriale": "276209",
            "tipo_bombola": "Recupero",
            "tara": 7.03,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "VUOTA"
        },
        {
            "tipo_gas": "R32",
            "id_interno": "201",
            "qta_presente": 0.0,
            "seriale": "28763",
            "tipo_bombola": "Cariche",
            "tara": 7.9,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "DDT. DD 05/08/2021",
            "data_revisione": "",
            "stato": "PROPRIA",
            "note": "Vuota solo per recupero"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "Recupero",
            "qta_presente": 0.0,
            "seriale": "241061",
            "tipo_bombola": "Recupero",
            "tara": 5.93,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "per recupero"
        },
        {
            "tipo_gas": "R32",
            "id_interno": "224",
            "qta_presente": 0.0,
            "seriale": "275449",
            "tipo_bombola": "Cariche",
            "tara": 6.09,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "RESTITUITA",
            "note": "GAS DA SMALTIRE"
        },
        {
            "tipo_gas": "Misto",
            "id_interno": "223",
            "qta_presente": 0.0,
            "seriale": "275449",
            "tipo_bombola": "Recupero",
            "tara": 6.08,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "GAS DA SMALTIRE"
        },
        {
            "tipo_gas": "Misto",
            "id_interno": "na1",
            "qta_presente": 0.0,
            "seriale": "241066",
            "tipo_bombola": "Recupero",
            "tara": 6.09,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "usata per recupero – da smaltire – vuota"
        },
        {
            "tipo_gas": "Misto",
            "id_interno": "na2",
            "qta_presente": 0.0,
            "seriale": "S51600",
            "tipo_bombola": "Recupero",
            "tara": 6.08,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "perde la valvola? Rotta?"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "na",
            "qta_presente": 0.0,
            "seriale": "241063",
            "tipo_bombola": "Cariche",
            "tara": 6.09,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "USATA PER RECUPERO 410? DA SMALTIRE"
        },
        {
            "tipo_gas": "Misto",
            "id_interno": "na3",
            "qta_presente": 0.0,
            "seriale": "S51600",
            "tipo_bombola": "Recupero",
            "tara": 6.09,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "perde la valvola? Rotta?"
        },
        {
            "tipo_gas": "Misto",
            "id_interno": "na4",
            "qta_presente": 0.0,
            "seriale": "241063",
            "tipo_bombola": "Recupero",
            "tara": 6.08,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": "DA SMALTIRE? – RECUPERO SOLO R410?"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "256",
            "qta_presente": 2.885,
            "seriale": "S5222179",
            "tipo_bombola": "Cariche",
            "tara": 7.61,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "02-07-2026",
            "ddt": "26002978",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": "Acquistate Nuove - Stoccate in Magazzino 18"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "257",
            "qta_presente": 10.78,
            "seriale": "S5300455",
            "tipo_bombola": "Cariche",
            "tara": 7.25,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "02-07-2026",
            "ddt": "26002978",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": "Acquistate Nuove - Stoccate in Magazzino 18"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "258",
            "qta_presente": 10.59,
            "seriale": "S5309052",
            "tipo_bombola": "Cariche",
            "tara": 7.25,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "02-07-2026",
            "ddt": "26002978",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": "Acquistate Nuove - Stoccate in Magazzino 18"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "259",
            "qta_presente": 10.08,
            "seriale": "S5304707",
            "tipo_bombola": "Cariche",
            "tara": 8.2,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "02-07-2026",
            "ddt": "26002978",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": "Acquistate Nuove - Stoccate in Magazzino 18"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "260",
            "qta_presente": 10.16,
            "seriale": "S5241219",
            "tipo_bombola": "Cariche",
            "tara": 7.53,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "02-07-2026",
            "ddt": "26002978",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": "Acquistate Nuove - Stoccate in Magazzino 18"
        },
        {
            "tipo_gas": "R410",
            "id_interno": "252",
            "qta_presente": 0.06,
            "seriale": "S5329281",
            "tipo_bombola": "Cariche",
            "tara": 7.25,
            "cap_lt": 12.5,
            "cap_kg": 10.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "234",
            "qta_presente": 6.12,
            "seriale": "F0298513",
            "tipo_bombola": "Cariche",
            "tara": 6.09,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "240",
            "qta_presente": 8.61,
            "seriale": "F0298270",
            "tipo_bombola": "Cariche",
            "tara": 6.09,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "NOLEGGIO",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "241",
            "qta_presente": 6.39,
            "seriale": "F0298273",
            "tipo_bombola": "Cariche",
            "tara": 6.09,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": ""
        },
        {
            "tipo_gas": "R32",
            "id_interno": "242",
            "qta_presente": 0.0,
            "seriale": "542474",
            "tipo_bombola": "Recupero",
            "tara": 6.09,
            "cap_lt": 11.25,
            "cap_kg": 9.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "SIAD",
            "data_acquisto": "24-07-2026",
            "ddt": "",
            "data_revisione": "",
            "stato": "PROPRIA",
            "note": ""
        },
        {
            "tipo_gas": "R424",
            "id_interno": "124",
            "qta_presente": 2.51,
            "seriale": "x",
            "tipo_bombola": "Cariche",
            "tara": 0.0,
            "cap_lt": 0.0,
            "cap_kg": 0.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "GASTEC",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": ""
        },
        {
            "tipo_gas": "R424",
            "id_interno": "192",
            "qta_presente": 6.62,
            "seriale": "x",
            "tipo_bombola": "Cariche",
            "tara": 0.0,
            "cap_lt": 0.0,
            "cap_kg": 0.0,
            "in_carico_a": "",
            "data_assegnazione": "",
            "fornitore": "GASTEC",
            "data_acquisto": "",
            "ddt": "",
            "data_revisione": "",
            "stato": "",
            "note": ""
        }
    ],
    "movimentazioni": []
}


# ==================== INIZIALIZZAZIONE SESSION STATE ====================

def init_data():
    if "data" not in st.session_state:
        dati_drive = carica_dati_drive()
        if dati_drive and "bombole" in dati_drive and "movimentazioni" in dati_drive:
            st.session_state.data = dati_drive
        else:
            st.session_state.data = DEFAULT_DATA.copy()
            st.session_state.data["config"] = DEFAULT_DATA["config"].copy()
            st.session_state.data["tecnici"] = [t.copy() for t in DEFAULT_DATA["tecnici"]]
            st.session_state.data["bombole"] = [b.copy() for b in DEFAULT_DATA["bombole"]]
            st.session_state.data["movimentazioni"] = [m.copy() for m in DEFAULT_DATA["movimentazioni"]]
            salva_dati_drive(st.session_state.data, silent=True)
        st.session_state.data_modified = False

init_data()

# Migrazione colori: forza i colori richiesti
COLORI_RICHIESTI = {"R32": "#C62828", "R410": "#F06292", "R407": "#795548", "R424": "#7B1FA2", "Misto": "#9E9E9E"}
colori_attuali = st.session_state.data.get("config", {}).get("colori_gas", {})
if colori_attuali != COLORI_RICHIESTI:
    st.session_state.data.setdefault("config", {})["colori_gas"] = COLORI_RICHIESTI.copy()
    salva_dati_drive(st.session_state.data, silent=True)


# ==================== AUTENTICAZIONE ====================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "password_ok" not in st.session_state:
    st.session_state.password_ok = False
if "tecnico_loggato" not in st.session_state:
    st.session_state.tecnico_loggato = None

# Fase 1: Password
if not st.session_state.password_ok:
    st.markdown('<div class="main-header">FGas Registro - Accesso</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Inserisci la password per accedere</div>', unsafe_allow_html=True)
    pwd = st.text_input("Password", type="password")
    if st.button("Accedi"):
        if pwd == "4444":
            st.session_state.password_ok = True
            st.rerun()
        else:
            st.error("Password errata")
    st.stop()

# Fase 2: Selezione tecnico
elif not st.session_state.authenticated:
    # Fallback tecnici di base (se nessun dato in memoria)
    TECNICI_FALLBACK = ["Pierluigi", "Yarema", "Gioele", "Terry", "Christian", "Manuel"]

    # Usa dati in memoria se disponibili (persistono tra logout/login nella stessa sessione browser)
    if "data" in st.session_state and "tecnici" in st.session_state.data:
        tec_list = [t["nome"] for t in st.session_state.data["tecnici"] if t.get("nome")]
    else:
        tec_list = TECNICI_FALLBACK

    st.markdown('<div class="main-header">Benvenuto in FGas Registro</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Seleziona il tecnico che sta accedendo</div>', unsafe_allow_html=True)

    if tec_list:
        tec_sel = st.selectbox("Tecnico", tec_list)

        # Controllo multi-accesso
        sessione = get_sessione_attiva_drive()
        if sessione and sessione.get("tecnico") != tec_sel:
            st.warning(f"⚠️ **{sessione['tecnico']}** e gia loggato (dal {sessione['timestamp'][:16].replace('T', ' ')}).")
            st.info("Contatta l'altro tecnico e chiedigli di effettuare il logout prima di accedere.")
            st.button("Entra nell'App", use_container_width=True, disabled=True)
        else:
            if st.button("Entra nell'App", use_container_width=True):
                st.session_state.tecnico_loggato = tec_sel
                st.session_state.authenticated = True
                set_sessione_attiva_drive(tec_sel)
                st.rerun()
    else:
        st.warning("Nessun tecnico in anagrafica. Verrai reindirizzato come amministratore.")
        if st.button("Entra come Amministratore", use_container_width=True):
            st.session_state.tecnico_loggato = "Amministratore"
            st.session_state.authenticated = True
            set_sessione_attiva_drive("Amministratore")
            st.rerun()
    st.stop()

# Lettura parametri QR da URL (deep link)
if "qr_payload" not in st.session_state:
    st.session_state.qr_payload = None
qp = st.query_params
if qp.get("qr_gas") and qp.get("qr_id"):
    st.session_state.qr_payload = {
        "v": "FGas1",
        "gas": qp.get("qr_gas", ""),
        "id": qp.get("qr_id", ""),
        "tipo": qp.get("qr_tipo", "Cariche"),
        "qta": float(qp.get("qr_qta", 0)),
        "seriale": qp.get("qr_seriale", "")
    }

st.markdown('<style>'
    '.main-header { font-size: 2.2rem; font-weight: 700; color: #0D47A1; margin-bottom: 0.2rem; } '
    '.sub-header { font-size: 1.1rem; color: #757575; margin-bottom: 1rem; } '
    '.kpi-card { padding: 1.2rem; border-radius: 16px; text-align: center; color: white; margin-bottom: 1rem; box-shadow: 0 4px 12px rgba(0,0,0,0.15); transition: transform 0.2s; } '
    '.kpi-card:hover { transform: translateY(-4px); } '
    '.kpi-value { font-size: 1.8rem; font-weight: 700; } '
    '.kpi-label { font-size: 0.9rem; opacity: 0.95; font-weight: 500; } '
    '.stButton>button { width: 100%; border-radius: 8px; } '
    '.drive-ok { color: #2E7D32; font-weight: 600; } '
    '.drive-ko { color: #C62828; font-weight: 600; } '
    '</style>', unsafe_allow_html=True)

if st.session_state.get("mobile_mode", False):
    st.markdown('<style>'
        '.main-header { font-size: 1.6rem !important; } '
        '.sub-header { font-size: 1rem !important; } '
        '.stButton>button { min-height: 52px !important; font-size: 1.1rem !important; } '
        'input, select, textarea { font-size: 1.05rem !important; } '
        '.kpi-value { font-size: 1.4rem !important; } '
        '.kpi-label { font-size: 0.8rem !important; } '
        'section[data-testid="stSidebar"] { width: 280px !important; } '
        '</style>', unsafe_allow_html=True)

GAS_COLORS = {"R32": "#C62828", "R410": "#F06292", "R407": "#795548", "R424": "#7B1FA2", "Misto": "#9E9E9E"}
GAS_LIST = ["R32", "R410", "R407", "R424", "Misto"]
# ==================== FUNZIONI UTILITY ====================
def get_kpi_gas(tipo_gas):
    movs = [m for m in st.session_state.data["movimentazioni"] if m["tipo_gas"] == tipo_gas]
    recuperi = sum(m["quantita"] for m in movs if m["tipo_mov"] == "RECUPERO")
    cariche = sum(m["quantita"] for m in movs if m["tipo_mov"] == "CARICA")
    ricariche = sum(m["quantita"] for m in movs if m["tipo_mov"] == "RICARICA")
    presente = sum(b["qta_presente"] for b in st.session_state.data["bombole"] if b["tipo_gas"] == tipo_gas)
    return recuperi, cariche, presente, ricariche

def get_bombole_gas(tipo_gas):
    return [b for b in st.session_state.data["bombole"] if b["tipo_gas"] == tipo_gas]

def get_all_gas():
    gas_list = []
    for b in st.session_state.data["bombole"]:
        if b["tipo_gas"] not in gas_list:
            gas_list.append(b["tipo_gas"])
    for g in GAS_LIST:
        if g not in gas_list:
            gas_list.append(g)
    return sorted(gas_list, key=lambda x: GAS_LIST.index(x) if x in GAS_LIST else 99)

def get_nome_tecnici():
    return [t["nome"] for t in st.session_state.data.get("tecnici", [])]

def get_colori_gas():
    return st.session_state.data.get("config", {}).get("colori_gas", GAS_COLORS)

def aggiorna_qta_bombola(tipo_gas, id_bombola, tipo_mov, quantita):
    for b in st.session_state.data["bombole"]:
        if b["tipo_gas"] == tipo_gas and b["id_interno"] == id_bombola:
            if tipo_mov == "CARICA":
                b["qta_presente"] = round(max(0, b["qta_presente"] - quantita), 3)
            elif tipo_mov in ("RECUPERO", "RICARICA"):
                b["qta_presente"] = round(b["qta_presente"] + quantita, 3)
            break

def aggiungi_movimentazione(mov, origine="MANUALE"):
    mov.setdefault("origine", origine)
    st.session_state.data["movimentazioni"].append(mov)
    aggiorna_qta_bombola(mov["tipo_gas"], mov["id_bombola"], mov["tipo_mov"], mov["quantita"])
    salva_dati_drive(st.session_state.data, silent=True)

def elimina_movimentazione(idx):
    mov = st.session_state.data["movimentazioni"][idx]
    for b in st.session_state.data["bombole"]:
        if b["tipo_gas"] == mov["tipo_gas"] and b["id_interno"] == mov["id_bombola"]:
            if mov["tipo_mov"] == "CARICA":
                b["qta_presente"] = round(b["qta_presente"] + mov["quantita"], 3)
            elif mov["tipo_mov"] in ("RECUPERO", "RICARICA"):
                b["qta_presente"] = round(max(0, b["qta_presente"] - mov["quantita"]), 3)
            break
    del st.session_state.data["movimentazioni"][idx]
    salva_dati_drive(st.session_state.data, silent=True)

def img_to_b64(img_file):
    if img_file is None:
        return ""
    return base64.b64encode(img_file.getvalue()).decode("utf-8")

def export_csv():
    output = io.StringIO()
    import csv
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["=== CRUSCOTTO KPI ==="])
    writer.writerow(["Gas", "Recuperi (kg)", "Cariche (kg)", "Ricariche (kg)", "Quantita Presente (kg)"])
    for gas in get_all_gas():
        rec, car, pres, ric = get_kpi_gas(gas)
        writer.writerow([gas, f"{rec:.2f}", f"{car:.2f}", f"{ric:.2f}", f"{pres:.2f}"])
    writer.writerow([])
    writer.writerow(["=== MATRICE BOMBOLA ==="])
    writer.writerow(["Gas", "ID Interno", "Qta Presente", "Seriale", "Tipo", "Tara", "Cap Lt", "Cap Kg",
                    "In Carico a", "Data Ass.", "Fornitore", "Data Acquisto", "DDT", "Data Rev.", "Stato", "Note"])
    for b in st.session_state.data["bombole"]:
        writer.writerow([
            b["tipo_gas"], b["id_interno"], b["qta_presente"], b.get("seriale",""),
            b.get("tipo_bombola",""), b.get("tara",""), b.get("cap_lt",""), b.get("cap_kg",""),
            b.get("in_carico_a",""), b.get("data_assegnazione",""), b.get("fornitore",""),
            b.get("data_acquisto",""), b.get("ddt",""), b.get("data_revisione",""),
            b.get("stato",""), b.get("note","")
        ])
    writer.writerow([])
    writer.writerow(["=== MOVIMENTAZIONI ==="])
    writer.writerow(["Data", "Gas", "ID Bombola", "Tipo Mov", "Quantita", "Cliente", "Tecnico", "Stoccaggio", "Note", "Origine"])
    for m in st.session_state.data["movimentazioni"]:
        writer.writerow([
            m["data"], m["tipo_gas"], m["id_bombola"], m["tipo_mov"], m["quantita"],
            m["cliente"], m["tecnico"], m["stoccaggio"], m["note"], m.get("origine", "MANUALE")
        ])
    writer.writerow([])
    writer.writerow(["=== TECNICI ==="])
    writer.writerow(["Nome", "Patentino", "Scadenza"])
    for t in st.session_state.data.get("tecnici", []):
        writer.writerow([t["nome"], t.get("patentino",""), t.get("scadenza","")])
    return output.getvalue()



# ==================== FUNZIONI QR CODE ====================
def genera_dati_qr(bombola, url_base=None):
    payload = {
        "v": "FGas1",
        "id": str(bombola["id_interno"]),
        "gas": bombola["tipo_gas"],
        "tipo": bombola.get("tipo_bombola", "Cariche"),
        "qta": float(bombola.get("qta_presente", 0)),
        "cap": float(bombola.get("cap_kg", 0)),
        "seriale": str(bombola.get("seriale", ""))
    }
    if url_base and url_base.strip():
        from urllib.parse import quote
        base = url_base.rstrip("/")
        qs = f"?qr_gas={quote(payload['gas'])}&qr_id={quote(payload['id'])}&qr_tipo={quote(payload['tipo'])}&qr_qta={payload['qta']}&qr_seriale={quote(payload['seriale'])}"
        return base + qs
    return json.dumps(payload, ensure_ascii=False)

def genera_immagine_qr(bombola, size=400, url_base=None):
    if not QR_AVAILABLE:
        return None
    dati = genera_dati_qr(bombola, url_base=url_base)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(dati)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    return img

def genera_html_stampa_qr(bombole, url_base=None):
    if not QR_AVAILABLE:
        return ""
    rows = ""
    for b in bombole:
        img = genera_immagine_qr(b, size=400, url_base=url_base)
        if img:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            color = GAS_COLORS.get(b["tipo_gas"], "#757575")
            rows += f"""
            <div class="qr-page">
                <div class="qr-header" style="background:{color};">
                    <h2>{b['tipo_gas']} — ID: {b['id_interno']}</h2>
                </div>
                <div class="qr-body">
                    <img src="data:image/png;base64,{b64}" class="qr-img" />
                    <div class="qr-info">
                        <p><strong>Seriale:</strong> {b.get('seriale','N/D')}</p>
                        <p><strong>Tipo:</strong> {b.get('tipo_bombola','N/D')}</p>
                        <p><strong>Qta:</strong> {b.get('qta_presente',0):.2f} / {b.get('cap_kg',0):.1f} kg</p>
                        <p><strong>Stato:</strong> {b.get('stato','N/D')}</p>
                    </div>
                </div>
                <div class="qr-footer">
                    P.RI.S.T — Priore Riccardo Servizio Termotecnico s.r.l.<br>
                    <small>Scansiona per registrare una movimentazione</small>
                </div>
            </div>
            """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>QR Code Bombole FGas</title>
        <style>
            @page {{ size: A4; margin: 0; }}
            body {{ margin: 0; font-family: Arial, sans-serif; background: #fff; }}
            .qr-page {{
                width: 210mm; height: 297mm;
                display: flex; flex-direction: column;
                align-items: center; justify-content: center;
                page-break-after: always; box-sizing: border-box;
                padding: 20mm;
            }}
            .qr-page:last-child {{ page-break-after: auto; }}
            .qr-header {{
                width: 100%; text-align: center; color: white;
                padding: 20px; border-radius: 16px 16px 0 0;
            }}
            .qr-header h2 {{ margin: 0; font-size: 2.4rem; }}
            .qr-body {{
                border: 3px solid #e0e0e0; border-top: none;
                width: 100%; text-align: center; padding: 40px 30px;
                border-radius: 0 0 16px 16px; background: #fafafa;
            }}
            .qr-img {{ width: 320px; height: 320px; image-rendering: pixelated; }}
            .qr-info {{ margin-top: 24px; font-size: 1.3rem; line-height: 2; color: #333; }}
            .qr-footer {{ margin-top: 40px; font-size: 1rem; color: #666; text-align: center; }}
            @media print {{
                .qr-page {{ page-break-after: always; }}
                body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            }}
        </style>
    </head>
    <body>{rows}</body>
    </html>
    """

def render_form_da_qr(payload):
    st.subheader("📋 Dati Bombola Rilevati")
    color = GAS_COLORS.get(payload.get("gas", ""), "#757575")
    st.markdown(
        f'<div style="padding:16px;border-radius:12px;border-left:6px solid {color};background:#f5f5f5;margin-bottom:16px;">'
        f'<div style="font-size:1.3rem;font-weight:700;color:{color};">{payload.get("gas", "N/D")} — ID {payload.get("id", "N/D")}</div>'
        f'<div style="margin-top:8px;color:#555;">'
        f'<b>Seriale:</b> {payload.get("seriale", "N/D")} &nbsp;|&nbsp; '
        f'<b>Tipo:</b> {payload.get("tipo", "N/D")} &nbsp;|&nbsp; '
        f'<b>Qta attuale:</b> {payload.get("qta", 0):.2f} kg'
        f'</div></div>',
        unsafe_allow_html=True
    )

    st.divider()
    st.subheader("✏️ Registra Movimentazione")
    tec_list = get_nome_tecnici()
    tec_default = st.session_state.get("tecnico_loggato", "")
    tec_index = tec_list.index(tec_default) if tec_default in tec_list else 0

    with st.form("form_mov_qr", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            data_mov = st.text_input("Data", value=datetime.now().strftime("%d-%m-%Y"))
            tipo_mov_sel = st.selectbox("Tipo Movimento", ["CARICA", "RECUPERO", "RICARICA"])
        with c2:
            quantita_mov = st.number_input("Quantita (kg)", min_value=0.0, step=0.01, format="%.3f")
            tecnico_sel = st.selectbox("Tecnico", tec_list, index=tec_index) if tec_list else st.text_input("Tecnico")
        with c3:
            cliente_mov = st.text_input("Cliente / Luogo")
            stoccaggio_mov = st.text_input("Stoccaggio Bombola")
        with c4:
            note_mov = st.text_input("Note")
        submitted = st.form_submit_button("✅ Registra Movimentazione da QR", use_container_width=True)
        if submitted:
            if quantita_mov <= 0:
                st.error("La quantita deve essere maggiore di zero!")
                return False
            mov = {
                "tipo_gas": payload["gas"],
                "id_bombola": payload["id"],
                "tipo_mov": tipo_mov_sel,
                "quantita": quantita_mov,
                "data": data_mov.strip(),
                "cliente": cliente_mov.strip(),
                "tecnico": tecnico_sel if tec_list else tecnico_sel.strip(),
                "stoccaggio": stoccaggio_mov.strip(),
                "note": note_mov.strip(),
                "foto_b64": ""
            }
            aggiungi_movimentazione(mov, origine="QR_CODE")
            st.success(f"Movimentazione {tipo_mov_sel} di {quantita_mov:.3f} kg registrata via QR Code!")
            st.balloons()
            return True
    return False

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("### 🔧 FGas Registro")
    st.markdown("*Gestione Carichi, Scarichi e Recuperi F-Gas*")
    st.divider()
    if st.session_state.get("tecnico_loggato"):
        st.markdown(f"👤 **Tecnico:** {st.session_state.tecnico_loggato}")
        if st.button("🚪 Logout", use_container_width=True):
            clear_sessione_attiva_drive()
            st.session_state.authenticated = False
            st.session_state.password_ok = False
            st.session_state.tecnico_loggato = None
            st.rerun()
        st.divider()
    svc = get_drive_service()
    if svc:
        st.markdown('<p class="drive-ok">🟢 Drive Connesso</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="drive-ko">🔴 Drive Non Connesso</p>', unsafe_allow_html=True)
        st.caption("Configura i Secrets per attivare il salvataggio su Drive")
    mobile = st.toggle("📱 Ottimizza per Cellulare", value=st.session_state.get("mobile_mode", False), key="mobile_toggle")
    if mobile != st.session_state.get("mobile_mode", False):
        st.session_state.mobile_mode = mobile
        st.rerun()
    st.divider()
    page = st.radio("Navigazione", [
        "Cruscotto KPI",
        "Anagrafica Tecnici",
        "Anagrafica Bombole",
        "Configurazione Colori",
        "Report Movimentazioni",
        "Movimentazione R32",
        "Movimentazione R410",
        "Movimentazione R407",
        "Movimentazione R424",
        "Movimentazione Misto",
        "Genera QR Code",
        "Scanner QR"
    ])
    st.divider()
    st.markdown("### Gestione Dati")
    if st.button("💾 Salva ora su Google Drive", use_container_width=True):
        if salva_dati_drive(st.session_state.data):
            st.success("Dati salvati su Drive!")
        else:
            st.error("Salvataggio fallito. Verifica i Secrets.")
    st.divider()
    json_data = json.dumps(st.session_state.data, indent=2, ensure_ascii=False)
    st.download_button(
        label="Scarica Backup JSON",
        data=json_data,
        file_name=f"FGas_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )
    csv_data = export_csv()
    st.download_button(
        label="Esporta CSV",
        data=csv_data,
        file_name=f"FGas_Registro_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
    uploaded = st.file_uploader("Carica Backup JSON", type=["json"])
    if uploaded is not None:
        try:
            imported = json.load(uploaded)
            if "bombole" in imported and "movimentazioni" in imported:
                st.session_state.data = imported
                salva_dati_drive(st.session_state.data, silent=True)
                st.success("Dati caricati e salvati su Drive!")
                st.rerun()
            else:
                st.error("File JSON non valido")
        except Exception as e:
            st.error(f"Errore caricamento: {e}")
    st.divider()
    st.markdown("<small>P.RI.S.T - v1.0 Drive</small>", unsafe_allow_html=True)

# ==================== CRUSCOTTO KPI ====================
if page == "Cruscotto KPI":
    st.markdown('<div style="font-size: 1.5rem; font-weight: 600; color: #0D47A1; margin-bottom: 1rem;">📊 Cruscotto KPI</div>', unsafe_allow_html=True)
    st.divider()

    # ========== ALERT ==========
    alert_count = 0
    alert_html = []
    oggi = datetime.now()
    for t in st.session_state.data.get("tecnici", []):
        scad = t.get("scadenza", "").strip()
        if scad:
            try:
                for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
                    try:
                        d = datetime.strptime(scad, fmt)
                        break
                    except ValueError:
                        continue
                giorni = (d - oggi).days
                if giorni < 0:
                    alert_html.append(f'<div style="background:#FFEBEE;color:#C62828;padding:10px 14px;border-radius:8px;margin-bottom:6px;font-weight:600;">⚠️ Patentino <b>{t["nome"]}</b> SCADUTO il {scad}!</div>')
                    alert_count += 1
                elif giorni <= 30:
                    alert_html.append(f'<div style="background:#FFF3E0;color:#E65100;padding:10px 14px;border-radius:8px;margin-bottom:6px;font-weight:600;">⏰ Patentino <b>{t["nome"]}</b> in scadenza tra {giorni} giorni ({scad})</div>')
                    alert_count += 1
            except Exception:
                pass

    for b in st.session_state.data["bombole"]:
        if b.get("tipo_bombola") == "Cariche" and b.get("qta_presente", 0) < 1.0 and b.get("qta_presente", 0) > 0:
            alert_html.append(f'<div style="background:#E3F2FD;color:#1565C0;padding:10px 14px;border-radius:8px;margin-bottom:6px;font-weight:600;">🔵 Bombola <b>{b["id_interno"]}</b> ({b["tipo_gas"]}) quasi vuota: {b["qta_presente"]:.2f} kg rimasti</div>')
            alert_count += 1
        elif b.get("tipo_bombola") == "Cariche" and b.get("qta_presente", 0) == 0:
            alert_html.append(f'<div style="background:#FFEBEE;color:#C62828;padding:10px 14px;border-radius:8px;margin-bottom:6px;font-weight:600;">🔴 Bombola <b>{b["id_interno"]}</b> ({b["tipo_gas"]}) <b>VUOTA</b> — necessaria ricarica</div>')
            alert_count += 1

    for b in st.session_state.data["bombole"]:
        if b.get("tipo_bombola") == "Recupero":
            cap = b.get("cap_kg", 0)
            qta = b.get("qta_presente", 0)
            if cap > 0 and qta >= cap * 0.8:
                alert_html.append(f'<div style="background:#E8F5E9;color:#2E7D32;padding:10px 14px;border-radius:8px;margin-bottom:6px;font-weight:600;">🟢 Bombola recupero <b>{b["id_interno"]}</b> ({b["tipo_gas"]}) quasi PIENA: {qta:.2f}/{cap:.1f} kg ({qta/cap*100:.0f}%)</div>')
                alert_count += 1

    if alert_count > 0:
        st.markdown(f'<div style="font-size:1.2rem;font-weight:700;color:#C62828;margin-bottom:8px;">🔔 Alert ({alert_count})</div>', unsafe_allow_html=True)
        for a in alert_html:
            st.markdown(a, unsafe_allow_html=True)
        st.divider()

    gas_list = get_all_gas()
    colori = get_colori_gas()
    cols = st.columns(len(gas_list))
    for i, gas in enumerate(gas_list):
        color = colori.get(gas, "#757575")
        rec, car, pres, ric = get_kpi_gas(gas)
        with cols[i]:
            st.markdown(
                f'<div class="kpi-card" style="background-color: {color};">'
                f'<div style="font-size: 1.3rem; font-weight: 700;">{gas}</div>'
                f'<div style="margin-top: 8px;"><div class="kpi-value">{rec:.2f} kg</div><div class="kpi-label">Recuperi</div></div>'
                f'<div style="margin-top: 6px;"><div class="kpi-value">{car:.2f} kg</div><div class="kpi-label">Cariche</div></div>'
                f'<div style="margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.3); padding-top: 6px;">'
                f'<div class="kpi-value" style="color: #FFF59D;">{pres:.2f} kg</div><div class="kpi-label">Presente</div></div>'
                f'</div>',
                unsafe_allow_html=True
            )
    st.divider()
    st.subheader("📦 Stato Bombole")
    bombole = st.session_state.data["bombole"]
    colori = get_colori_gas()

    # Gestione selezione bombola
    if "bombola_selezionata" not in st.session_state:
        st.session_state.bombola_selezionata = None

    if bombole:
        n_cols = 1 if st.session_state.get("mobile_mode", False) else 3
        for i in range(0, len(bombole), n_cols):
            cols = st.columns(n_cols)
            for j, b in enumerate(bombole[i:i+n_cols]):
                with cols[j]:
                    gas = b.get("tipo_gas", "")
                    color = colori.get(gas, "#757575")
                    cap = b.get("cap_kg", 0)
                    qta = b.get("qta_presente", 0)
                    tipo = b.get("tipo_bombola", "Cariche")
                    stato = b.get("stato", "")
                    carico = b.get("in_carico_a", "")
                    note = b.get("note", "")
                    bid = b.get("id_interno", "")

                    if cap > 0:
                        pct = min(100, max(0, (qta / cap) * 100))
                        pct_norm = pct / 100.0
                        if tipo == "Cariche":
                            bar_color = "normal" if pct > 50 else "warning" if pct > 20 else "error"
                        else:
                            bar_color = "error" if pct > 80 else "warning" if pct > 50 else "normal"
                    else:
                        pct = None
                        pct_norm = 0.0
                        bar_color = "error"

                    stato_badge = f'<span style="background:{color};color:white;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;">{stato}</span>' if stato else ''

                    st.markdown(
                        f'<div style="border:1px solid #e0e0e0;border-radius:12px;padding:16px;margin-bottom:12px;background:#fafafa;">'
                        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
                        f'<div style="width:14px;height:14px;border-radius:50%;background:{color};"></div>'
                        f'<div style="font-size:1.15rem;font-weight:700;color:{color};">{gas}</div>'
                        f'<div style="margin-left:auto;font-size:0.85rem;color:#666;">{tipo}</div>'
                        f'</div>'
                        f'<div style="font-size:0.95rem;margin-bottom:6px;"><b>ID:</b> {bid} &nbsp;|&nbsp; <b>Seriale:</b> {b.get("seriale","")}</div>'
                        f'<div style="font-size:0.9rem;color:#555;margin-bottom:8px;">{stato_badge}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                    if pct is not None:
                        st.progress(pct_norm, text=f"{pct:.0f}% — {qta:.2f} / {cap:.1f} kg")
                    else:
                        st.caption("⚠️ Capacita non definita")

                    if carico:
                        st.caption(f"👤 In carico a: **{carico}**")
                    if note:
                        st.caption(f"📝 {note}")

                    # Pulsante dettagli
                    if st.button("📋 Dettagli", key=f"det_{gas}_{bid}", use_container_width=True):
                        st.session_state.bombola_selezionata = b
                        st.rerun()

                    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

        # Sezione dettagli bombola selezionata
        if st.session_state.bombola_selezionata:
            bs = st.session_state.bombola_selezionata
            st.divider()
            bcolor = colori.get(bs.get("tipo_gas", ""), "#757575")
            st.markdown(
                f'<div style="padding:20px;border-radius:16px;border-left:6px solid {bcolor};background:#f8f9fa;margin-bottom:16px;">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                f'<div style="font-size:1.5rem;font-weight:700;color:{bcolor};">{bs.get("tipo_gas","")} — ID {bs.get("id_interno","")}</div>'
                f'<div style="font-size:0.9rem;color:#666;">{bs.get("tipo_bombola","")}</div>'
                f'</div>'
                f'<div style="margin-top:10px;color:#555;">'
                f'<b>Seriale:</b> {bs.get("seriale","N/D")} &nbsp;|&nbsp; '
                f'<b>Qta:</b> {bs.get("qta_presente",0):.2f} / {bs.get("cap_kg",0):.1f} kg &nbsp;|&nbsp; '
                f'<b>Stato:</b> {bs.get("stato","N/D")} &nbsp;|&nbsp; '
                f'<b>In carico a:</b> {bs.get("in_carico_a","Nessuno")}'
                f'</div></div>',
                unsafe_allow_html=True
            )

            # Movimentazioni della bombola
            movs_bombola = [m for m in st.session_state.data["movimentazioni"] 
                           if m["id_bombola"] == bs["id_interno"] and m["tipo_gas"] == bs["tipo_gas"]]
            if movs_bombola:
                st.subheader(f"📄 Movimentazioni ({len(movs_bombola)})")
                df_mov_bom = pd.DataFrame(movs_bombola)
                df_mov_bom = df_mov_bom.sort_values(by="data", ascending=False)
                st.dataframe(
                    df_mov_bom[["data", "tipo_mov", "quantita", "cliente", "tecnico", "stoccaggio", "note", "origine"]],
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("Nessuna movimentazione registrata per questa bombola.")

            if st.button("❌ Chiudi Dettagli", use_container_width=True):
                st.session_state.bombola_selezionata = None
                st.rerun()
    else:
        st.info("Nessuna bombola inserita.")

    # ========== GRAFICI ==========
    st.divider()
    st.subheader("📈 Andamento Consumo e Recupero F-Gas")
    movs = st.session_state.data["movimentazioni"]
    if movs:
        try:
            import matplotlib.pyplot as plt
            import matplotlib
            matplotlib.rcParams['font.size'] = 9
            MPL_AVAILABLE = True
        except ImportError:
            MPL_AVAILABLE = False
            st.info("📊 I grafici richiedono `matplotlib`. Aggiungilo al requirements.txt per visualizzarli.")

        if MPL_AVAILABLE:
            df_all = pd.DataFrame(movs)
            def parse_date(d):
                for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
                    try:
                        return datetime.strptime(d, fmt)
                    except ValueError:
                        continue
                return None
            df_all["dt"] = df_all["data"].apply(parse_date)
            df_all = df_all.dropna(subset=["dt"])
            if not df_all.empty:
                df_all = df_all.sort_values("dt")
                df_all["anno_mese"] = df_all["dt"].dt.strftime("%Y-%m")
                fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))
                cariche = df_all[df_all["tipo_mov"] == "CARICA"].groupby(["anno_mese", "tipo_gas"])["quantita"].sum().unstack(fill_value=0)
                if not cariche.empty:
                    cariche.plot(kind="bar", stacked=True, ax=axes[0], color=[colori.get(c, "#757575") for c in cariche.columns])
                    axes[0].set_title("Cariche F-Gas per Mese", fontweight="bold")
                    axes[0].set_xlabel("Mese")
                    axes[0].set_ylabel("kg")
                    axes[0].legend(title="Gas", bbox_to_anchor=(1.02, 1), loc="upper left")
                    axes[0].tick_params(axis="x", rotation=45)
                else:
                    axes[0].text(0.5, 0.5, "Nessuna carica registrata", ha="center", va="center", transform=axes[0].transAxes)
                    axes[0].set_title("Cariche F-Gas per Mese")
                recuperi = df_all[df_all["tipo_mov"] == "RECUPERO"].groupby(["anno_mese", "tipo_gas"])["quantita"].sum().unstack(fill_value=0)
                if not recuperi.empty:
                    recuperi.plot(kind="bar", stacked=True, ax=axes[1], color=[colori.get(c, "#757575") for c in recuperi.columns])
                    axes[1].set_title("Recuperi F-Gas per Mese", fontweight="bold")
                    axes[1].set_xlabel("Mese")
                    axes[1].set_ylabel("kg")
                    axes[1].legend(title="Gas", bbox_to_anchor=(1.02, 1), loc="upper left")
                    axes[1].tick_params(axis="x", rotation=45)
                else:
                    axes[1].text(0.5, 0.5, "Nessun recupero registrato", ha="center", va="center", transform=axes[1].transAxes)
                    axes[1].set_title("Recuperi F-Gas per Mese")
                plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("Nessuna movimentazione con data valida per i grafici.")
    else:
        st.info("Nessuna movimentazione registrata.")

    st.divider()
    st.subheader("Ultime 20 Movimentazioni")
    df_mov = pd.DataFrame(st.session_state.data["movimentazioni"])
    if not df_mov.empty:
        df_mov = df_mov.sort_values(by="data", ascending=False).head(20)
        st.dataframe(
            df_mov[["data", "tipo_gas", "id_bombola", "tipo_mov", "quantita", "cliente", "tecnico", "stoccaggio", "note", "origine"]],
            use_container_width=True, hide_index=True
        )

# ==================== ANAGRAFICA TECNICI ====================
if page == "Anagrafica Tecnici":
    st.markdown('<div class="main-header">Anagrafica Tecnici</div>', unsafe_allow_html=True)
    st.divider()
    with st.form("form_tecnico", clear_on_submit=True):
        st.subheader("Aggiungi Nuovo Tecnico")
        c1, c2, c3 = st.columns(3)
        with c1:
            nome_tec = st.text_input("Nome Tecnico")
        with c2:
            pat_tec = st.text_input("N Patentino")
        with c3:
            scad_tec = st.text_input("Scadenza (GG/MM/AAAA)")
        submitted = st.form_submit_button("Aggiungi Tecnico", use_container_width=True)
        if submitted and nome_tec.strip():
            st.session_state.data["tecnici"].append({
                "nome": nome_tec.strip(), "patentino": pat_tec.strip(), "scadenza": scad_tec.strip()
            })
            salva_dati_drive(st.session_state.data, silent=True)
            st.success(f"Tecnico {nome_tec} aggiunto!")
            st.rerun()
    st.divider()
    st.subheader("Elenco Tecnici")
    df_tec = pd.DataFrame(st.session_state.data["tecnici"])
    if not df_tec.empty:
        edited_tec = st.data_editor(
            df_tec, use_container_width=True, hide_index=True, num_rows="dynamic",
            column_config={
                "nome": st.column_config.TextColumn("Nome", required=True),
                "patentino": st.column_config.TextColumn("Patentino"),
                "scadenza": st.column_config.TextColumn("Scadenza")
            }
        )
        if st.button("Salva Modifiche Tecnici", use_container_width=True):
            st.session_state.data["tecnici"] = edited_tec.to_dict("records")
            salva_dati_drive(st.session_state.data, silent=True)
            st.success("Tecnici aggiornati!")
            st.rerun()
    else:
        st.info("Nessun tecnico inserito")

# ==================== ANAGRAFICA BOMBOLA ====================
if page == "Anagrafica Bombole":
    st.markdown('<div class="main-header">Anagrafica Bombole - Matrice</div>', unsafe_allow_html=True)
    st.divider()
    # Info ultimo ID
    ultimo_id = st.session_state.data.get("config", {}).get("ultimo_id_bombola", 0)
    st.info(f"🔢 Ultimo ID assegnato: **{ultimo_id}** — Prossimo consigliato: **{ultimo_id + 1}**")
    ids_esistenti = [b["id_interno"] for b in st.session_state.data["bombole"]]
    tec_list = get_nome_tecnici()

    with st.form("form_bombola", clear_on_submit=True):
        st.subheader("Aggiungi Nuova Bombola")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            gas_bom = st.selectbox("Tipo Gas", GAS_LIST)
            id_bom = st.text_input("ID Interno", value=str(ultimo_id + 1))
            seriale = st.text_input("Seriale")
        with c2:
            tipo_bom = st.selectbox("Tipo Bombola", ["Cariche", "Recupero"])
            tara = st.number_input("Tara (kg)", min_value=0.0, step=0.01, format="%.2f")
            cap_kg = st.number_input("Capacita Max (Kg)", min_value=0.0, step=0.1, format="%.1f")
        with c3:
            carico = st.selectbox("In Carico a", [""] + tec_list) if tec_list else st.text_input("In Carico a")
            data_ass = st.text_input("Data Assegnazione")
            fornitore = st.text_input("Fornitore")
        with c4:
            data_acq = st.text_input("Data Acquisto/Noleggio")
            ddt = st.text_input("DDT / Doc. Riferimento")
            data_rev = st.text_input("Data Prossima Revisione")
        c5, c6 = st.columns(2)
        with c5:
            stato_bom = st.selectbox("Stato", ["", "NOLEGGIO", "PROPRIA", "RESTITUITA", "DISMESSA", "In Uso", "In Attesa Ritiro", "IN MANUTENZIONE"])
        with c6:
            note_bom = st.text_area("Note", height=100)
        submitted = st.form_submit_button("Aggiungi Bombola", use_container_width=True)
        if submitted and id_bom.strip():
            if id_bom.strip() in ids_esistenti:
                st.error(f"⚠️ L'ID '{id_bom.strip()}' è già assegnato a un'altra bombola! Scegli un ID diverso.")
            else:
                st.session_state.data["bombole"].append({
                    "tipo_gas": gas_bom, "id_interno": id_bom.strip(), "qta_presente": 0.0,
                    "seriale": seriale.strip(), "tipo_bombola": tipo_bom,
                    "tara": tara, "cap_lt": 0.0, "cap_kg": cap_kg,
                    "in_carico_a": carico, "data_assegnazione": data_ass.strip(),
                    "fornitore": fornitore.strip(), "data_acquisto": data_acq.strip(),
                    "ddt": ddt.strip(), "data_revisione": data_rev.strip(),
                    "stato": stato_bom, "note": note_bom.strip()
                })
                try:
                    num_id = int(id_bom.strip())
                    if num_id > st.session_state.data.get("config", {}).get("ultimo_id_bombola", 0):
                        st.session_state.data.setdefault("config", {})["ultimo_id_bombola"] = num_id
                except ValueError:
                    pass
                salva_dati_drive(st.session_state.data, silent=True)
                st.success(f"Bombola {id_bom} ({gas_bom}) aggiunta!")
                st.rerun()
    st.divider()
    st.subheader("Matrice Bombole")
    df_bom = pd.DataFrame(st.session_state.data["bombole"])
    if not df_bom.empty:
        # Filtri
        with st.expander("🔍 Filtri Bombole", expanded=False):
            fc1, fc2, fc3, fc4 = st.columns(4)
            with fc1:
                filtro_gas_bom = st.multiselect("Tipo Gas", sorted(df_bom["tipo_gas"].unique()), default=[])
            with fc2:
                filtro_tipo_bom = st.multiselect("Tipo Bombola", sorted(df_bom["tipo_bombola"].unique()), default=[])
            with fc3:
                filtro_stato_bom = st.multiselect("Stato", sorted([s for s in df_bom["stato"].unique() if s]), default=[])
            with fc4:
                filtro_id_bom = st.text_input("Cerca ID / Seriale", value="", placeholder="es. 250 o S5301225")

        df_filt_bom = df_bom.copy()
        if filtro_gas_bom:
            df_filt_bom = df_filt_bom[df_filt_bom["tipo_gas"].isin(filtro_gas_bom)]
        if filtro_tipo_bom:
            df_filt_bom = df_filt_bom[df_filt_bom["tipo_bombola"].isin(filtro_tipo_bom)]
        if filtro_stato_bom:
            df_filt_bom = df_filt_bom[df_filt_bom["stato"].isin(filtro_stato_bom)]
        if filtro_id_bom.strip():
            q = filtro_id_bom.strip().lower()
            df_filt_bom = df_filt_bom[
                df_filt_bom["id_interno"].astype(str).str.lower().str.contains(q) |
                df_filt_bom["seriale"].astype(str).str.lower().str.contains(q)
            ]

        st.markdown(f"**Bombole visualizzate:** {len(df_filt_bom)} / {len(df_bom)}")

        tec_list = get_nome_tecnici()
        edited_bom = st.data_editor(
            df_filt_bom, use_container_width=True, hide_index=True, num_rows="dynamic",
            column_config={
                "tipo_gas": st.column_config.SelectboxColumn("Gas", options=GAS_LIST, required=True),
                "id_interno": st.column_config.TextColumn("ID Interno", required=True),
                "qta_presente": st.column_config.NumberColumn("Qta Presente", format="%.2f"),
                "seriale": st.column_config.TextColumn("Seriale"),
                "tipo_bombola": st.column_config.SelectboxColumn("Tipo", options=["Cariche", "Recupero"]),
                "tara": st.column_config.NumberColumn("Tara", format="%.2f"),
                "cap_kg": st.column_config.NumberColumn("Cap Kg", format="%.1f"),
                "in_carico_a": st.column_config.SelectboxColumn("In Carico a", options=[""] + tec_list) if tec_list else st.column_config.TextColumn("In Carico a"),
                "stato": st.column_config.SelectboxColumn("Stato", options=["", "NOLEGGIO", "PROPRIA", "RESTITUITA", "DISMESSA", "In Uso", "In Attesa Ritiro", "IN MANUTENZIONE"])
            }
        )
        if st.button("Salva Modifiche Matrice", use_container_width=True):
            # Ricostruisci l'elenco completo: sostituisci le righe filtrate e lascia le altre
            df_completo = df_bom.copy()
            if not df_filt_bom.empty:
                for idx, row in df_filt_bom.iterrows():
                    mask = (df_completo["tipo_gas"] == row["tipo_gas"]) & (df_completo["id_interno"] == row["id_interno"])
                    if mask.any():
                        df_completo.loc[mask] = row
            st.session_state.data["bombole"] = df_completo.to_dict("records")
            salva_dati_drive(st.session_state.data, silent=True)
            st.success("Matrice bombole aggiornata!")
            st.rerun()
    else:
        st.info("Nessuna bombola inserita")

# ==================== MOVIMENTAZIONI GAS ====================
def render_movimentazione_page(tipo_gas):
    color = get_colori_gas().get(tipo_gas, "#757575")
    st.markdown(f'<div class="main-header" style="color: {color};">Movimentazione {tipo_gas}</div>', unsafe_allow_html=True)
    st.divider()
    bombole_gas = get_bombole_gas(tipo_gas)
    codici = [b["id_interno"] for b in bombole_gas]
    tec_list = get_nome_tecnici()
    if not codici:
        st.warning(f"Nessuna bombola trovata per {tipo_gas}. Aggiungine una dall'Anagrafica Bombole.")
        return
    with st.form(f"form_mov_{tipo_gas}", clear_on_submit=True):
        st.subheader("Nuova Movimentazione")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            data_mov = st.text_input("Data", value=datetime.now().strftime("%d-%m-%Y"))
            id_bombola_sel = st.selectbox("ID Bombola", codici)
        with c2:
            tipo_mov_sel = st.selectbox("Tipo Movimento", ["CARICA", "RECUPERO"])
            quantita_mov = st.number_input("Quantita (kg)", min_value=0.0, step=0.01, format="%.3f")
        with c3:
            cliente_mov = st.text_input("Cliente / Luogo")
            tecnico_sel = st.selectbox("Tecnico", tec_list) if tec_list else st.text_input("Tecnico")
        with c4:
            stoccaggio_mov = st.text_input("Stoccaggio Bombola")
            note_mov = st.text_input("Note")
        submitted = st.form_submit_button("Aggiungi Movimentazione", use_container_width=True)
        if submitted:
            if quantita_mov <= 0:
                st.error("La quantita deve essere maggiore di zero!")
            else:
                mov = {
                    "tipo_gas": tipo_gas,
                    "id_bombola": id_bombola_sel,
                    "tipo_mov": tipo_mov_sel,
                    "quantita": quantita_mov,
                    "data": data_mov.strip(),
                    "cliente": cliente_mov.strip(),
                    "tecnico": tecnico_sel if tec_list else tecnico_sel.strip(),
                    "stoccaggio": stoccaggio_mov.strip(),
                    "note": note_mov.strip(),
                    "foto_b64": ""
                }
                aggiungi_movimentazione(mov)
                st.success(f"Movimentazione {tipo_mov_sel} di {quantita_mov:.3f} kg aggiunta!")
                st.rerun()
    st.divider()
    st.subheader("Storico Movimentazioni")
    movs = [m for m in st.session_state.data["movimentazioni"] if m["tipo_gas"] == tipo_gas]
    if movs:
        df_mov = pd.DataFrame(movs)
        df_mov = df_mov.iloc[::-1].reset_index(drop=True)
        for idx, row in df_mov.iterrows():
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 3, 3, 1])
                with col1:
                    st.markdown(f"**{row['tipo_mov']}** - {row['quantita']:.3f} kg")
                    st.caption(f"Bombola: {row['id_bombola']} | Data: {row['data']}")
                with col2:
                    st.markdown(f"Cliente: {row['cliente']}")
                    st.caption(f"Tecnico: {row['tecnico']} | Stoccaggio: {row['stoccaggio']}")
                with col3:
                    st.caption(f"Note: {row['note']}")
                with col4:
                    global_idx = None
                    for gi, m in enumerate(st.session_state.data["movimentazioni"]):
                        if (m["tipo_gas"] == tipo_gas and m["data"] == row["data"] and 
                            m["id_bombola"] == row["id_bombola"] and m["quantita"] == row["quantita"] and
                            m["tipo_mov"] == row["tipo_mov"]):
                            global_idx = gi
                            break
                    if st.button("🗑️", key=f"del_{tipo_gas}_{idx}"):
                        if global_idx is not None:
                            elimina_movimentazione(global_idx)
                            st.rerun()
        st.divider()
        st.subheader("Tabella Completa Movimentazioni")
        st.dataframe(
            df_mov[["data", "id_bombola", "tipo_mov", "quantita", "cliente", "tecnico", "stoccaggio", "note"]],
            use_container_width=True, hide_index=True
        )
    else:
        st.info(f"Nessuna movimentazione per {tipo_gas}")

# Render pagine movimentazione
if page == "Movimentazione R32":
    render_movimentazione_page("R32")
if page == "Movimentazione R410":
    render_movimentazione_page("R410")
if page == "Movimentazione R407":
    render_movimentazione_page("R407")
if page == "Movimentazione R424":
    render_movimentazione_page("R424")
if page == "Movimentazione Misto":
    render_movimentazione_page("Misto")

# ==================== CONFIGURAZIONE COLORI ====================
if page == "Configurazione Colori":
    st.markdown('<div class="main-header">🎨 Configurazione Colori Gas</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Personalizza i colori associati a ogni tipo di gas per il cruscotto e le movimentazioni</div>', unsafe_allow_html=True)
    st.divider()
    colori = get_colori_gas()
    gas_list = get_all_gas()
    if gas_list:
        cols = st.columns(min(len(gas_list), 3))
        for i, gas in enumerate(gas_list):
            with cols[i % 3]:
                current_color = colori.get(gas, "#757575")
                new_color = st.color_picker(f"Colore {gas}", current_color, key=f"cp_{gas}")
                colori[gas] = new_color
                st.markdown(f'<div style="width:100%; height:30px; background-color:{new_color}; border-radius:6px; margin-top:4px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);"></div>', unsafe_allow_html=True)
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Salva Colori", use_container_width=True):
                st.session_state.data.setdefault("config", {})["colori_gas"] = colori
                salva_dati_drive(st.session_state.data, silent=True)
                st.success("Colori aggiornati e salvati su Drive!")
                st.rerun()
        with c2:
            if st.button("🔄 Ripristina Default", use_container_width=True):
                default_colori = {"R32": "#C62828", "R410": "#F06292", "R407": "#795548", "R424": "#7B1FA2", "Misto": "#9E9E9E"}
                st.session_state.data.setdefault("config", {})["colori_gas"] = default_colori
                salva_dati_drive(st.session_state.data, silent=True)
                st.success("Colori ripristinati ai valori predefiniti!")
                st.rerun()
    else:
        st.info("Nessun tipo di gas trovato.")

# ==================== REPORT MOVIMENTAZIONI ====================
if page == "Report Movimentazioni":
    st.markdown('<div class="main-header">📄 Report Movimentazioni</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Filtra, visualizza e stampa le movimentazioni F-Gas</div>', unsafe_allow_html=True)
    st.divider()

    movs = st.session_state.data["movimentazioni"]
    if not movs:
        st.info("Nessuna movimentazione registrata.")
    else:
        df_all = pd.DataFrame(movs)
        tec_list = sorted([t for t in df_all["tecnico"].unique() if t])
        gas_list_all = sorted([g for g in df_all["tipo_gas"].unique() if g])

        with st.expander("🔍 Filtri", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                filtro_gas = st.multiselect("Gas", gas_list_all, default=[])
                id_list = sorted([str(i) for i in df_all["id_bombola"].unique() if i])
                filtro_id_bombola = st.multiselect("ID Bombola", id_list, default=[])
            with c2:
                filtro_tec = st.multiselect("Tecnico", tec_list, default=[])
            with c3:
                filtro_tipo = st.multiselect("Tipo Movimento", ["CARICA", "RECUPERO", "RICARICA"], default=[])
                filtro_origine = st.multiselect("Origine", ["MANUALE", "QR_CODE"], default=[])
            with c4:
                filtro_data_da = st.text_input("Data da (GG-MM-YYYY)", value="")
                filtro_data_a = st.text_input("Data a (GG-MM-YYYY)", value="")

        df_filt = df_all.copy()
        if filtro_gas:
            df_filt = df_filt[df_filt["tipo_gas"].isin(filtro_gas)]
        if filtro_tec:
            df_filt = df_filt[df_filt["tecnico"].isin(filtro_tec)]
        if filtro_tipo:
            df_filt = df_filt[df_filt["tipo_mov"].isin(filtro_tipo)]
        if filtro_data_da.strip():
            df_filt = df_filt[df_filt["data"] >= filtro_data_da.strip()]
        if filtro_data_a.strip():
            df_filt = df_filt[df_filt["data"] <= filtro_data_a.strip()]
        if filtro_origine:
            df_filt = df_filt[df_filt.get("origine", "MANUALE").isin(filtro_origine)]
        if filtro_id_bombola:
            df_filt = df_filt[df_filt["id_bombola"].astype(str).isin(filtro_id_bombola)]

        st.markdown(f"**Movimentazioni trovate:** {len(df_filt)}")
        if not df_filt.empty:
            st.dataframe(
                df_filt[["data", "tipo_gas", "id_bombola", "tipo_mov", "quantita", "cliente", "tecnico", "stoccaggio", "note", "origine"]],
                use_container_width=True, hide_index=True
            )
            colori = get_colori_gas()
            html_rows = ""
            for _, row in df_filt.iterrows():
                bg = colori.get(row["tipo_gas"], "#757575")
                html_rows += f"""
                <tr>
                    <td style="border:1px solid #ddd;padding:8px;">{row['data']}</td>
                    <td style="border:1px solid #ddd;padding:8px;background:{bg};color:white;font-weight:600;">{row['tipo_gas']}</td>
                    <td style="border:1px solid #ddd;padding:8px;">{row['id_bombola']}</td>
                    <td style="border:1px solid #ddd;padding:8px;">{row['tipo_mov']}</td>
                    <td style="border:1px solid #ddd;padding:8px;text-align:right;">{row['quantita']:.3f} kg</td>
                    <td style="border:1px solid #ddd;padding:8px;">{row['cliente']}</td>
                    <td style="border:1px solid #ddd;padding:8px;">{row['tecnico']}</td>
                    <td style="border:1px solid #ddd;padding:8px;">{row['stoccaggio']}</td>
                    <td style="border:1px solid #ddd;padding:8px;">{row['note']}</td>
                    <td style="border:1px solid #ddd;padding:8px;text-align:center;font-weight:600;">{row.get('origine','MANUALE')}</td>
                </tr>
                """
            html_report = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Report FGas</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    h1 {{ color: #0D47A1; }}
                    table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                    th {{ background: #0D47A1; color: white; padding: 10px; text-align: left; }}
                    td {{ font-size: 0.9rem; }}
                    .footer {{ margin-top: 30px; font-size: 0.8rem; color: #666; }}
                </style>
            </head>
            <body>
                <h1>📄 Report Movimentazioni F-Gas</h1>
                <p><strong>Data generazione:</strong> {datetime.now().strftime('%d-%m-%Y %H:%M')}</p>
                <p><strong>Totale movimentazioni:</strong> {len(df_filt)}</p>
                <table>
                    <thead>
                        <tr>
                            <th>Data</th><th>Gas</th><th>ID Bombola</th><th>Tipo</th>
                            <th>Quantità</th><th>Cliente</th><th>Tecnico</th><th>Stoccaggio</th><th>Note</th><th>Origine</th>
                        </tr>
                    </thead>
                    <tbody>{html_rows}</tbody>
                </table>
                <div class="footer">P.RI.S.T - Priore Riccardo Servizio Termotecnico s.r.l.</div>
                <script>window.print();</script>
            </body>
            </html>
            """
            st.download_button(
                label="🖨️ Scarica Report per Stampa",
                data=html_report,
                file_name=f"Report_FGas_{datetime.now().strftime('%Y%m%d')}.html",
                mime="text/html"
            )
        else:
            st.warning("Nessuna movimentazione corrisponde ai filtri selezionati.")

# ==================== GENERA QR CODE ====================
if page == "Genera QR Code":
    st.markdown('<div class="main-header">🏷️ Genera QR Code Bombole</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Seleziona le bombole, genera i QR code e stampali su A4</div>', unsafe_allow_html=True)
    st.divider()

    if not QR_AVAILABLE:
        st.error("⚠️ Libreria `qrcode` non installata. Aggiungi `qrcode[pil]` al requirements.txt")
        st.stop()

    st.subheader("🔗 URL dell'App")
    # Leggi URL salvato
    url_salvato = st.session_state.data.get("config", {}).get("url_base_app", "")
    c1, c2 = st.columns([4, 1])
    with c1:
        url_base = st.text_input(
            "Inserisci l'URL base della tua app Streamlit (es. https://tua-app.streamlit.app)",
            value=url_salvato,
            placeholder="https://tua-app.streamlit.app",
            key="url_base_input"
        )
    with c2:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("💾 Salva URL", use_container_width=True):
            st.session_state.data.setdefault("config", {})["url_base_app"] = url_base.strip()
            salva_dati_drive(st.session_state.data, silent=True)
            st.success("URL salvato!")
            st.rerun()
    if url_base.strip():
        st.success("✅ I QR code conterranno URL diretti. Scansionandoli con qualsiasi lettore QR si aprira' l'app gia' precompilata.")
    else:
        st.info("ℹ️ Se lasci vuoto, i QR conterranno solo il testo JSON (da copiare manualmente).")
    st.divider()

    df_bom = pd.DataFrame(st.session_state.data["bombole"])
    if df_bom.empty:
        st.info("Nessuna bombola presente.")
        st.stop()

    df_bom["Seleziona"] = False
    df_display = df_bom[["Seleziona", "tipo_gas", "id_interno", "seriale", "tipo_bombola", "qta_presente", "cap_kg", "stato"]]

    st.subheader("Seleziona le bombole da stampare")
    edited = st.data_editor(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Seleziona": st.column_config.CheckboxColumn("Stampa", default=False),
            "tipo_gas": st.column_config.TextColumn("Gas"),
            "id_interno": st.column_config.TextColumn("ID"),
            "seriale": st.column_config.TextColumn("Seriale"),
            "tipo_bombola": st.column_config.TextColumn("Tipo"),
            "qta_presente": st.column_config.NumberColumn("Qta", format="%.2f"),
            "cap_kg": st.column_config.NumberColumn("Cap", format="%.1f"),
            "stato": st.column_config.TextColumn("Stato"),
        },
        disabled=["tipo_gas", "id_interno", "seriale", "tipo_bombola", "qta_presente", "cap_kg", "stato"]
    )

    selezionate = edited[edited["Seleziona"] == True]
    st.markdown(f"**Bombole selezionate:** {len(selezionate)}")

    if len(selezionate) > 0:
        if st.button("🖨️ Genera QR Code per Stampa", use_container_width=True):
            bombole_obj = selezionate.to_dict("records")
            html_stampa = genera_html_stampa_qr(bombole_obj, url_base=url_base.strip() or None)
            st.download_button(
                label="📄 Scarica HTML per Stampa A4",
                data=html_stampa,
                file_name=f"QR_Bombole_{datetime.now().strftime('%Y%m%d')}.html",
                mime="text/html"
            )
            st.success("HTML generato! Clicca sul pulsante sopra per scaricarlo e stampare (una bombola per pagina A4).")
            st.info("💡 Suggerimento: nel browser, usa **Stampa → Salva come PDF** per ottenere un PDF pronto.")
    else:
        st.info("Seleziona almeno una bombola dalla tabella.")

# ==================== SCANNER QR ====================
if page == "Scanner QR":
    st.markdown('<div class="main-header">📱 Scanner QR Code</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Registra una movimentazione scansionando il QR code con qualsiasi lettore del cellulare</div>', unsafe_allow_html=True)
    st.divider()

    payload = st.session_state.get("qr_payload", None)

    if payload:
        st.success("✅ QR Code rilevato dall'URL!")
        st.divider()
        bombola_trovata = None
        for b in st.session_state.data["bombole"]:
            if b["id_interno"] == payload["id"] and b["tipo_gas"] == payload["gas"]:
                bombola_trovata = b
                break

        if bombola_trovata:
            payload["qta"] = float(bombola_trovata.get("qta_presente", 0))
            payload["tipo"] = bombola_trovata.get("tipo_bombola", "Cariche")
            payload["stato"] = bombola_trovata.get("stato", "")
            render_form_da_qr(payload)
        else:
            st.error(f"⚠️ Bombola {payload['id']} ({payload['gas']}) non trovata nell'anagrafica attuale. Potrebbe essere stata eliminata o l'ID e' cambiato.")
            st.info("Dati rilevati dal QR:")
            st.json(payload)
    else:
        st.info("📲 **Come funziona:**")
        st.markdown('''
        1. **Genera i QR code** dalla pagina **"Genera QR Code"** inserendo l'URL della tua app.
        2. **Stampa e appiccica** le etichette sulle bombole.
        3. **Scansiona** il QR con qualsiasi lettore QR del tuo cellulare.
        4. **Si aprira' direttamente questa pagina** con i dati della bombola gia' precompilati.
        5. **Registra** la movimentazione in pochi secondi.
        ''')
        st.divider()
        st.subheader("⌨️ Inserimento manuale (fallback)")
        testo_qr = st.text_area("Incolla qui il contenuto del QR code (testo JSON o URL)", height=120)
        if testo_qr.strip():
            try:
                p = json.loads(testo_qr.strip())
                if p.get("v", "").startswith("FGas"):
                    st.session_state.qr_payload = p
                    st.rerun()
                else:
                    st.error("❌ Formato QR non riconosciuto.")
            except Exception:
                try:
                    from urllib.parse import parse_qs, urlparse
                    parsed = urlparse(testo_qr.strip())
                    qs = parse_qs(parsed.query)
                    if qs.get("qr_gas") and qs.get("qr_id"):
                        st.session_state.qr_payload = {
                            "v": "FGas1",
                            "gas": qs.get("qr_gas", [""])[0],
                            "id": qs.get("qr_id", [""])[0],
                            "tipo": qs.get("qr_tipo", ["Cariche"])[0],
                            "qta": float(qs.get("qr_qta", ["0"])[0]),
                            "seriale": qs.get("qr_seriale", [""])[0]
                        }
                        st.rerun()
                    else:
                        st.error("❌ URL non valido o parametri QR mancanti.")
                except Exception:
                    st.error("❌ Il testo incollato non e' un JSON valido ne' un URL con parametri QR.")
