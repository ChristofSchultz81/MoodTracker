import datetime as dt
import io

import pandas as pd
import requests
import streamlit as st


APP_TITLE = "Persönlicher MoodTracker"
CSV_COLUMNS = [
    "Date",
    "Mood",
    "Energy",
    "Stress",
    "SleepQuality",
    "SocialConnection",
    "Note",
]
MOOD_CRITERIA = {
    "Mood": "Grundstimmung",
    "Energy": "Energie",
    "Stress": "Stress",
    "SleepQuality": "Schlafqualität",
    "SocialConnection": "Sozial verbunden",
}


def get_settings() -> tuple[str, str, str]:
    """Liest die Nextcloud-Konfiguration aus Streamlit Secrets."""
    url = st.secrets.get("NC_URL", "").strip().rstrip("/")
    user = st.secrets.get("NC_USER", "").strip()
    password = st.secrets.get("NC_PASS", "")
    return url, user, password


def csv_url(base_url: str) -> str:
    """Erzeugt die URL für die CSV-Datei im MoodTracker-Ordner."""
    return f"{base_url}/MoodTracker/mood_entries.csv"


def load_entries(base_url: str, user: str, password: str) -> pd.DataFrame:
    """Lädt Einträge aus Nextcloud oder erstellt eine leere Tabelle."""
    try:
        response = requests.get(
            csv_url(base_url),
            auth=(user, password),
            timeout=20,
        )
    except requests.RequestException as error:
        st.error(f"Nextcloud ist nicht erreichbar: {error}")
        return pd.DataFrame(columns=CSV_COLUMNS)

    if response.status_code == 404:
        return pd.DataFrame(columns=CSV_COLUMNS)
    if response.status_code != 200:
        st.error(f"Nextcloud-Ladefehler: HTTP {response.status_code}")
        return pd.DataFrame(columns=CSV_COLUMNS)

    try:
        entries = pd.read_csv(io.StringIO(response.text))
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=CSV_COLUMNS)

    for column in CSV_COLUMNS:
        if column not in entries.columns:
            entries[column] = ""
    return entries[CSV_COLUMNS]


def save_entries(
    entries: pd.DataFrame, base_url: str, user: str, password: str
) -> bool:
    """Speichert alle Stimmungseinträge als CSV in Nextcloud."""
    csv_buffer = io.StringIO()
    entries.to_csv(csv_buffer, index=False)
    try:
        response = requests.put(
            csv_url(base_url),
            data=csv_buffer.getvalue().encode("utf-8"),
            auth=(user, password),
            headers={"Content-Type": "text/csv; charset=utf-8"},
            timeout=20,
        )
    except requests.RequestException as error:
        st.error(f"Speichern in Nextcloud fehlgeschlagen: {error}")
        return False

    if response.status_code not in (200, 201, 204):
        st.error(f"Nextcloud-Speicherfehler: HTTP {response.status_code}")
        return False
    return True


def main() -> None:
    """Baut die Streamlit-Oberfläche für Stimmungseinträge und Auswertung."""
    st.set_page_config(page_title=APP_TITLE, page_icon="🌤️", layout="centered")
    st.title(APP_TITLE)
    st.write(
        "Halte täglich fest, wie du dich fühlst. Die Werte reichen von 1 "
        "(niedrig) bis 10 (hoch)."
    )

    base_url, user, password = get_settings()
    if not all((base_url, user, password)):
        st.error(
            "Bitte hinterlege NC_URL, NC_USER und NC_PASS in den "
            "Streamlit Secrets. "
            "NC_URL muss auf den Nextcloud-WebDAV-Basisordner zeigen."
        )
        st.code(
            '[secrets]\n'
            'NC_URL = "https://cloud.example/remote.php/dav/files/USER"\n'
            'NC_USER = "dein-benutzername"\n'
            'NC_PASS = "dein-app-passwort"'
        )
        return

    entries = load_entries(base_url, user, password)

    with st.form("mood_entry_form"):
        entry_date = st.date_input("Datum", value=dt.date.today())
        st.subheader("Meine fünf Stimmungskriterien")
        values: dict[str, int] = {}
        for key, label in MOOD_CRITERIA.items():
            values[key] = st.slider(label, min_value=1, max_value=10, value=5)
        note = st.text_area("Notiz (optional)", max_chars=500)
        submitted = st.form_submit_button("Stimmung speichern")

    if submitted:
        new_entry = pd.DataFrame(
            [
                {
                    "Date": entry_date.isoformat(),
                    **values,
                    "Note": note.strip(),
                }
            ],
            columns=CSV_COLUMNS,
        )
        updated_entries = pd.concat([entries, new_entry], ignore_index=True)
        if save_entries(updated_entries, base_url, user, password):
            st.success("Stimmung wurde in Nextcloud gespeichert.")
            st.rerun()

    st.divider()
    st.subheader("Stimmung im Zeitverlauf")
    if entries.empty:
        st.info("Noch keine Stimmungseinträge vorhanden.")
        return

    chart_data = entries.copy()
    chart_data["Date"] = pd.to_datetime(chart_data["Date"], errors="coerce")
    chart_data["Mood"] = pd.to_numeric(chart_data["Mood"], errors="coerce")
    chart_data = chart_data.dropna(subset=["Date", "Mood"])
    chart_data = (
        chart_data.groupby("Date", as_index=True)["Mood"].mean().sort_index()
    )
    st.line_chart(
        chart_data,
        y="Mood",
        y_label="Grundstimmung (1-10)",
        x_label="Datum",
    )


if __name__ == "__main__":
    main()
