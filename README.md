# imap-notion-sync

Sincronizza automaticamente le email da un server IMAP verso un database Notion.

Questo repository fornisce un'applicazione Docker che legge messaggi IMAP, estrae metadati e crea pagine in un database Notion per tracciare e archiviare le email.

**Principali vantaggi**
- Sincronizzazione automatica in batch
- Gestione dei metadati (mittente, oggetto, data, message-id)
- Compatibilità con HTML/quoted-printable e charset multipli
- Plugin runtime per personalizzare il filtering senza ricostruire l'immagine

**Nota**: il README è in italiano; se preferisci una versione in inglese posso aggiungerla.

**Quick Start**
- **Prerequisiti**: `docker`, `docker-compose`, account Notion e accesso IMAP.
- Crea un file `.env` con le variabili minime (vedi sotto).
- Avvia con `docker run` o `docker-compose up -d`.

**Essenziali (.env example)**
```env
# Notion
NOTION_TOKEN=your_notion_token_here
LINE_ITEMS_DATABASE_ID=your_database_id_here

# IMAP
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your_email@gmail.com
IMAP_PASSWORD=your_app_password

# Config
IMAP_FOLDERS=INBOX
SYNC_SINCE_DAYS=30
BATCH_SIZE=50
POLL_INTERVAL=60
LOG_LEVEL=INFO
# Attachments
ATTACHMENTS_DIR=./attachments
# If you host the attachments under a public URL, set the base URL so the app
# can attach them to Notion as external files. Example: https://cdn.example.com/imap-files
ATTACHMENTS_BASE_URL=
```

**Database Notion (consigliato)**
- Crea un database con queste proprietà base:
  - `Subject` (Title)
  - `From` (Rich Text)
  - `Body` (Rich Text)
  - `Message-ID` (Rich Text)
  - `Email Date` (Date)

**Uso Docker (rapido)**
- Costruisci l'immagine:
```bash
docker build -t ghcr.io/carminelau/imap-notion-sync:latest .
```
- Esegui con `.env`:
```bash
docker run --env-file .env ghcr.io/carminelau/imap-notion-sync:latest
```

**Docker Compose (consigliato: usa `.env`)**
Esempio minimo `docker-compose.yml`:
```yaml
services:
  imap-notion-sync:
    build: .
    env_file: .env
    restart: "no"
```

Avvio:
```bash
docker-compose up -d
```

Sicurezza: evita di inserire token/credenziali in chiaro nel `docker-compose.yml` in produzione; usa sempre `.env` o secret manager.

**Plugin runtime (personalizzare senza rebuild)**
- Puoi fornire un modulo plugin che implementa `should_create_page(meta, body)` e montarlo nel container.
- File di esempio inclusi: `start_with_plugin.py` e `custom_filter.py`.

Esempio `docker run` che monta il plugin:
```bash
docker run --env-file .env --name imap-custom \
  -v "$PWD/custom_filter.py":/app/custom_filter.py:ro \
  -v "$PWD/start_with_plugin.py":/app/start_with_plugin.py:ro \
  --entrypoint python ghcr.io/carminelau/imap-notion-sync:latest /app/start_with_plugin.py
```

Esempio `docker-compose` (plugin):
```yaml
version: "3.8"
services:
  imap-notion-sync:
    image: ghcr.io/carminelau/imap-notion-sync:latest
    env_file: .env
    volumes:
      - ./custom_filter.py:/app/custom_filter.py:ro
      - ./start_with_plugin.py:/app/start_with_plugin.py:ro
    entrypoint: ["python","/app/start_with_plugin.py"]
```

Opzioni utili per plugin:
- `CUSTOM_FILTER_MODULE`: nome del modulo plugin (default `custom_filter`).
- il plugin può restituire `dict` con `properties_override` se il wrapper è adattato per applicarle.

**Come funziona (breve)**
- Connessione IMAP (SSL/TLS)
- Ricerca mail a partire da `SYNC_SINCE_DAYS` o dall'ultima sincronizzazione
- Download in batch e parsing (multipart, charset, QP, HTML)
- Creazione pagina Notion per ogni messaggio (con gestione rate-limit)

Segnalazione: l'implementazione filtra i messaggi usando UID quando possibile e verifica `INTERNALDATE` per assicurare il rispetto di `SYNC_SINCE_DAYS`.

**Configurazioni avanzate**
- `IMAP_FOLDERS`: cartelle da sincronizzare (es. `INBOX,Spedizioni`)
- `SYNC_SINCE_DAYS`: quanti giorni indietro sincronizzare
- `BATCH_SIZE`: numero di email per batch
- `POLL_INTERVAL`: secondi tra controlli
- `ATTACHMENTS_DIR`: directory nel container dove salvare gli allegati (monta un volume per persistenza)
- `ATTACHMENTS_BASE_URL`: base URL pubblico per servire gli allegati; se impostato gli allegati saranno aggiunti a Notion come file `external`.

Notion Direct Upload (opzionale)
- `NOTION_UPLOAD_FILES`: `true|false` (default `false`). Se impostato a `true` il servizio proverà a caricare gli allegati direttamente su Notion usando il metodo "Uploading small files". Se l'upload ha successo, l'allegato verrà referenziato in Notion tramite un `file_upload` ID.
- `NOTION_VERSION`: stringa per l'header `Notion-Version` (default `2025-09-03`).

Note sul comportamento e limiti:
- Il flusso diretto supporta file fino a 20 MB (limite della guida "Uploading small files").
- Dopo la creazione dell'oggetto di upload Notion fornisce un `upload_url` con `expiry_time` (circa 1 ora). Il file deve essere caricato e allegato entro questo intervallo; lo script carica e crea la pagina subito dopo per rispettare il vincolo.
- Se l'upload diretto fallisce e `ATTACHMENTS_BASE_URL` è impostato, l'applicazione utilizzerà l'URL esterno come fallback. Se nessun fallback è disponibile, il file verrà comunque salvato in `ATTACHMENTS_DIR` e verrà loggato l'errore.

**Troubleshooting rapida**
- "Connection refused": controlla host/porta/firewall
- "Authentication failed": verifica credenziali e password app (Gmail)
- "Invalid token" (Notion): verifica integrazione e token
- Nessuna email sincronizzata: verifica variabili `.env` e log del container

Comandi utili per log:
```bash
docker logs -f imap-notion-sync
docker-compose logs -f imap-notion-sync
docker logs --tail 200 imap-notion-sync
docker logs imap-notion-sync 2>&1 | grep -i error
```

Consiglio: imposta `LOG_LEVEL=DEBUG` per debug più dettagliato.

**Dipendenze principali**
- `notion-client` (client Notion)
- `beautifulsoup4` (HTML -> testo)
 - `requests` (HTTP client usato per il flusso di upload diretto su Notion)
- Standard library: `imaplib`, `email`, `ssl`

**Licenza & Contribuire**
- Licenza: MIT (vedi `LICENSE`)
- Contribuzioni: apri issue o PR; suggerimenti e bug sono benvenuti.

---

Se vuoi posso:
- aggiungere una versione in inglese
- estrarre la sezione "Plugin" in un file separato `PLUGIN.md`
- includere esempi `custom_filter.py` più completi

Fammi sapere quale di queste preferisci e aggiorno il README ancora.
