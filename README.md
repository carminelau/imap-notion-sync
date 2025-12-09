# imap-notion-sync

🔄 **Sincronizzazione automatica di email IMAP verso Notion**

Un'applicazione Docker che estrae email da un server IMAP e sincronizza automaticamente tutti i messaggi in un database Notion. Perfetto per archiviare, organizzare e tenere traccia delle email importanti.

## 🎯 Funzionalità

- **Connessione IMAP**: Accesso sicuro a qualsiasi server IMAP (Gmail, Outlook, etc.)
- **Sincronizzazione completa**: Importa tutte le email con i metadati
- **Estrazione metadati**: Recupera automaticamente mittente, oggetto, data e corpo
- **Sincronizzazione Notion**: Crea pagine nel database Notion per ogni email
- **Rate limiting**: Gestisce automaticamente i limiti di API di Notion
- **Batch processing**: Elabora le email in batch per migliore performance
- **Filtro temporale**: Sincronizza solo le email degli ultimi N giorni configurabili

## 📋 Requisiti

- Docker e Docker Compose
- Account Notion con database configurato
- Server IMAP accessibile
- Token di autenticazione Notion

## 🚀 Installazione e Utilizzo

### 1. Configurazione del Database Notion

Crea un database in Notion con le seguenti proprietà:

| Proprietà | Tipo | Descrizione |
|-----------|------|-------------|
| Subject | Title | Oggetto dell'email |
| From | Rich Text | Mittente |
| Body | Rich Text | Corpo dell'email |
| Message-ID | Rich Text | ID univoco email |
| Email Date | Date | Data ricezione |

### 2. Variabili di Ambiente

Crea un file `.env` con le seguenti variabili:

```env
# Notion
NOTION_TOKEN=your_notion_token_here
LINE_ITEMS_DATABASE_ID=your_database_id_here

# IMAP
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your_email@gmail.com
IMAP_PASSWORD=your_app_password

# Configurazione
IMAP_FOLDERS=INBOX,Spedizioni
SYNC_SINCE_DAYS=30
BATCH_SIZE=50
```

#### Come ottenere le credenziali:

**Notion Token:**
1. Vai a https://www.notion.so/my-integrations
2. Crea una nuova integrazione
3. Copia il token da "Internal Integration Secret"
4. Aggiungi l'integrazione al tuo database Notion

**Database ID:**
- Apri il tuo database in Notion
- L'ID è visibile nell'URL: `https://www.notion.so/[ID]?v=...`

**IMAP Credentials:**
- Per Gmail: usa la password di app (2FA richiesto)
- Per altri provider: usa le credenziali standard IMAP

### 3. Esecuzione con Docker

#### Docker diretto

```bash
# Build dell'immagine
docker build -t ghcr.io/carminelau/imap-notion-sync:latest .

# Run del container
docker run --env-file .env ghcr.io/carminelau/imap-notion-sync:latest
```

#### Docker Compose - Versione con .env

Usa il file `.env` per le variabili (scelta consigliata per la sicurezza):

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  imap-notion-sync:
    build: .
    container_name: ghcr.io/carminelau/imap-notion-sync:latest
    env_file: .env
    restart: no
    networks:
      - sync-network

networks:
  sync-network:
    driver: bridge
```

**.env:**
```env
NOTION_TOKEN=your_notion_token_here
LINE_ITEMS_DATABASE_ID=your_database_id_here
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your_email@gmail.com
IMAP_PASSWORD=your_app_password
IMAP_FOLDERS=INBOX,Spedizioni
SYNC_SINCE_DAYS=30
BATCH_SIZE=50
```

Esecuzione:
```bash
docker-compose up -d
```

#### Docker Compose - Versione con parametri in chiaro

Se preferisci specifiche tutto nel compose (meno sicuro, non usare in produzione):

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  imap-notion-sync:
    build: .
    container_name: ghcr.io/carminelau/imap-notion-sync:latest
    environment:
      # Notion
      NOTION_TOKEN: your_notion_token_here
      LINE_ITEMS_DATABASE_ID: your_database_id_here
      
      # IMAP
      IMAP_HOST: imap.gmail.com
      IMAP_PORT: "993"
      IMAP_USER: your_email@gmail.com
      IMAP_PASSWORD: your_app_password
      
      # Configurazione
      IMAP_FOLDERS: "INBOX,Spedizioni"
      SYNC_SINCE_DAYS: "30"
      BATCH_SIZE: "50"
    
    restart: no
    networks:
      - sync-network

networks:
  sync-network:
    driver: bridge
```

Esecuzione:
```bash
docker-compose up -d
```

⚠️ **Nota sulla sicurezza**: La versione con parametri in chiaro nel compose espone le credenziali nel file. Usa sempre la versione con `.env` in produzione!

## 🔧 Come Funziona

### Flusso di Sincronizzazione

1. **Connessione IMAP**: Si connette al server IMAP con SSL/TLS
2. **Ricerca Email**: Cerca email dal numero di giorni configurato
3. **Elaborazione Batch**: Scarica le email in batch per performance
4. **Parsing Email**:
   - Estrae il Message-ID
   - Decodifica il corpo (plain text o HTML)
   - Parsa i metadati (Mittente, Oggetto, Data, etc.)
5. **Sincronizzazione Notion**: 
   - Crea una nuova pagina per ogni email nel database

### Decodifica Automatica

L'applicazione gestisce automaticamente:

- **Quoted-Printable**: Email codificate QP
- **HTML Content**: Converte HTML a testo pulito
- **Multiple Charsets**: UTF-8, ISO-8859-1, e altri
- **Multipart Messages**: Email con testo e allegati

## 📊 Configurazioni Avanzate

### IMAP_FOLDERS
Specifica le cartelle IMAP da sincronizzare (default: `INBOX`):
```env
IMAP_FOLDERS=INBOX,Spedizioni,Archivio
```

### SYNC_SINCE_DAYS
Numero di giorni indietro da cui sincronizzare (default: `30`):
```env
SYNC_SINCE_DAYS=7  # Ultimi 7 giorni
```

### BATCH_SIZE
Numero di email da elaborare per batch (default: `50`):
```env
BATCH_SIZE=100  # Batch più grandi
```

## 🐛 Troubleshooting

### "Connection refused" - IMAP
- Verifica che l'host IMAP sia raggiungibile
- Controlla la porta (di solito 993 per IMAPS)
- Verifica che il firewall non blocchi la connessione

### "Authentication failed" - IMAP
- Verifica username e password
- Per Gmail, assicurati di usare una password di app (non la password dell'account)
- Verifica che IMAP sia abilitato nel server

### "Invalid token" - Notion
- Verifica il token in https://www.notion.so/my-integrations
- Assicurati che l'integrazione sia aggiunta al database
- Il token scade? Generane uno nuovo

### Nessuna email sincronizzata
- Verifica che il database Notion esista e sia raggiungibile
- Controlla che le variabili di ambiente siano corrette
- Verifica i log del container per errori di parsing

## 📝 Decodifica Email

L'applicazione gestisce automaticamente:

- **Quoted-Printable**: Email codificate QP
- **HTML Content**: Converte HTML a testo pulito
- **Multiple Charsets**: UTF-8, ISO-8859-1, e altri
- **Multipart Messages**: Email con testo e allegati

## 📦 Dipendenze

- `notion-client`: Client Python ufficiale di Notion
- `beautifulsoup4`: Parsing HTML
- Standard library: `imaplib`, `email`, `ssl`

## 📄 Licenza

MIT License - Vedi LICENSE per dettagli

## 🤝 Contributi

Segnala bug e suggerimenti come issues!

---

**Nota**: Questa applicazione è progettata per sincronizzare email generiche. Personalizza il database Notion in base alle tue esigenze specifiche.

## 📣 Visualizzare i log Docker

Di seguito i comandi utili per leggere i log del container e debug tramite `docker logs`.

- Se hai avviato con `docker-compose` (usa il nome del servizio o del container):

```bash
# Vedi i log del servizio in background
docker-compose logs -f imap-notion-sync

# Oppure, se preferisci il nome del container
docker logs -f imap-notion-sync
```

- Se hai avviato con `docker run` (container chiamato `imap-notion-sync`):

```bash
docker logs -f imap-notion-sync
```

- Mostrare gli ultimi N record dei log:

```bash
docker logs --tail 200 imap-notion-sync
```

- Se vuoi filtrare o cercare testo specifico nei log (es. error):

```bash
docker logs imap-notion-sync 2>&1 | grep -i error
```

Consiglio: imposta `LOG_LEVEL=DEBUG` nel tuo `.env` per maggiori dettagli mentre fai troubleshooting.
