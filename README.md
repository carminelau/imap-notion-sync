# imap-notion-sync

🔄 **Sincronizzazione automatica di email IMAP verso Notion**

Un'applicazione Docker che estrae email da un server IMAP e sincronizza i dati dei materiali/articoli in un database Notion. Perfetto per automatizzare la gestione degli ordini e degli articoli spediti.

## 🎯 Funzionalità

- **Connessione IMAP**: Accesso sicuro a qualsiasi server IMAP (Gmail, Outlook, etc.)
- **Parsing intelligente**: Estrae automaticamente articoli, quantità, varianti e SKU dalle email
- **Estrazione metadati**: Recupera ordini, tracking numbers e dati di spedizione
- **Sincronizzazione Notion**: Crea e aggiorna automaticamente pagine nel database Notion
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
| Material | Title | Nome dell'articolo |
| Qty | Number | Quantità |
| Variant | Text | Variante (colore, taglia, etc.) |
| SKU | Text | Codice SKU |
| Order ID | Text | ID ordine |
| Tracking | Text | Numero di tracking |
| Message-ID | Text | ID messaggio email |
| Email Date | Date | Data della email |

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
docker build -t imap-notion-sync .

# Run del container
docker run --env-file .env imap-notion-sync
```

#### Docker Compose - Versione con .env

Usa il file `.env` per le variabili (scelta consigliata per la sicurezza):

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  imap-notion-sync:
    build: .
    container_name: imap-notion-sync
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
    container_name: imap-notion-sync
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
   - Parsa i metadati (Data, Mittente, etc.)
5. **Parsing Articoli**: Estrae automaticamente:
   - Nome articolo
   - Quantità (pattern: "X di Y")
   - Varianti (colore, taglia, etc.)
   - SKU
   - Order ID e Tracking number
6. **Sincronizzazione Notion**: 
   - Cerca articoli esistenti (match per Message-ID + Material)
   - Aggiorna se esiste, crea se nuovo

### Pattern di Parsing

L'applicazione riconosce automaticamente:

```
Articoli in questa spedizione
- Maglietta Rossa × 2
  L / Rosso
  SKU123456
  1 di 2

Ordine: ORD-123456
Numero di Tracking: TRACK-987654
```

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

### Articoli non trovati
- Verifica il pattern delle email (deve contenere "Articoli in questa spedizione")
- Controlla i log per il parsing
- Verifica che i campi del database corrispondano a quelli attesi

## 📝 Decodifica Email

L'applicazione gestisce automaticamente:

- **Quoted-Printable**: Email codificate QP
- **HTML Content**: Converte HTML a testo pulito
- **Multiple Charsets**: UTF-8, ISO-8859-1, e altri
- **Multipart Messages**: Email con testo e allegati

## 🔐 Sicurezza

- ✅ SSL/TLS per connessioni IMAP
- ✅ Variabili di ambiente per credenziali (mai in hardcode)
- ✅ Nessun log di credenziali
- ✅ Rate limiting per API di Notion

## 📦 Dipendenze

- `notion-client`: Client Python ufficiale di Notion
- `beautifulsoup4`: Parsing HTML
- Standard library: `imaplib`, `email`, `ssl`

## 📄 Licenza

MIT License - Vedi LICENSE per dettagli

## 🤝 Contributi

Segnala bug e suggerimenti come issues!

---

**Nota**: Questa applicazione è progettata per sincronizzare email da fornitori di spedizioni. Adatta i pattern di parsing in base al tuo formato email specifico.
