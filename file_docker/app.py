# app.py
import os, ssl, time, email, re, json, sys
import logging
from datetime import datetime, timezone, timedelta
from imaplib import IMAP4_SSL
from html import unescape
from bs4 import BeautifulSoup
from notion_client import Client

# --- Config ---
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
LINE_DB_ID = os.environ["LINE_ITEMS_DATABASE_ID"]
IMAP_HOST = os.environ["IMAP_HOST"]
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER = os.environ["IMAP_USER"]
IMAP_PASSWORD = os.environ["IMAP_PASSWORD"]
FOLDERS = [f.strip() for f in os.environ.get("IMAP_FOLDERS", "INBOX").split(",") if f.strip()]
SINCE_DAYS = int(os.environ.get("SYNC_SINCE_DAYS", "30"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "50"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))  # seconds between polls when running continuously
PROCESSED_STORE_PATH = os.environ.get("PROCESSED_STORE_PATH", "./processed.json")
SEEN_MAX = int(os.environ.get("SEEN_MAX", "10000"))

notion = Client(auth=NOTION_TOKEN)

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(stream=sys.stdout, level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("imap-notion-sync")

# --- Utils di decodifica ---
def qp_decode(s: bytes|str, charset="utf-8"):
	if isinstance(s, str):
		s = s.encode("utf-8", errors="ignore")
	try:
		return email.quoprimime.body_decode(s).decode(charset, "replace")
	except Exception:
		try:
			return s.decode(charset, "replace")
		except Exception:
			return s.decode("utf-8", "replace")

def html_to_text(html_str: str) -> str:
	try:
		soup = BeautifulSoup(html_str, "html.parser")
		for br in soup.find_all(["br","p","div","tr"]):
			br.append("\n")
		text = soup.get_text(separator=" ")
		return unescape(" ".join(text.split()))
	except Exception:
		return " ".join(unescape(html_str).split())

def get_best_body(msg) -> tuple[str,str]:
	plain, html = "", ""
	if msg.is_multipart():
		for part in msg.walk():
			ct = part.get_content_type()
			if ct in ("text/plain","text/html"):
				cs = part.get_content_charset() or "utf-8"
				payload = part.get_payload(decode=True) or b""
				txt = qp_decode(payload, cs)
				if ct == "text/plain" and not plain:
					plain = " ".join(txt.split())
				elif ct == "text/html" and not html:
					html = txt
	else:
		ct = msg.get_content_type()
		cs = msg.get_content_charset() or "utf-8"
		payload = msg.get_payload(decode=True) or b""
		txt = qp_decode(payload, cs)
		if ct == "text/plain":
			plain = " ".join(txt.split())
		elif ct == "text/html":
			html = txt
	text = plain or html_to_text(html)
	return text, html


# --- Duplicate persistence (simple file store) ---
def load_store(path: str) -> dict:
	try:
		with open(path, "r", encoding="utf-8") as f:
			return json.load(f)
	except Exception:
		return {"folders": {}, "msgids": []}

def save_store(path: str, store: dict):
	try:
		tmp = path + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump(store, f)
		os.replace(tmp, path)
	except Exception:
		logger.exception("Failed saving processed store to %s", path)

def is_seen(store: dict, uid: str, msgid: str, folder: str) -> bool:
	if msgid:
		if msgid in store.get("msgids", []):
			return True
	fdata = store.setdefault("folders", {})
	ulist = fdata.setdefault(folder, {}).get("uids", [])
	if uid and uid in ulist:
		return True
	return False

def mark_seen(store: dict, uid: str, msgid: str, folder: str):
	fdata = store.setdefault("folders", {})
	folder_entry = fdata.setdefault(folder, {})
	ulist = folder_entry.setdefault("uids", [])
	if uid and (not ulist or ulist[-1] != uid):
		ulist.append(uid)
	if msgid:
		mids = store.setdefault("msgids", [])
		if not mids or mids[-1] != msgid:
			mids.append(msgid)
	# trim
	if len(ulist) > SEEN_MAX:
		folder_entry["uids"] = ulist[-SEEN_MAX:]
	mids = store.get("msgids", [])
	if len(mids) > SEEN_MAX:
		store["msgids"] = mids[-SEEN_MAX:]

# --- IMAP ---
def imap_search_since(imap, folder, since_date):
	typ, _ = imap.select(f'"{folder}"', readonly=True)
	if typ != "OK":
		return []
	crit = since_date.strftime("%d-%b-%Y")
	# Prefer UID SEARCH so results are UIDs compatible with later `uid('fetch', ...)`.
	# Some servers/clients return sequence numbers for `search()` which would
	# not match `uid('fetch', ...)` and cause fetching of wrong messages.
	used_uid = False
	decoded = []
	try:
		typ, data = imap.uid('search', None, 'SINCE', crit)
		if typ == 'OK' and data and data[0]:
			uids = data[0].split()
			decoded = [uid.decode() for uid in uids]
			used_uid = True
			logger.debug("UID search returned %d ids (sample: %s)", len(decoded), decoded[:5])
		else:
			logger.debug("UID search returned no data or non-OK: typ=%s", typ)
	except Exception:
		logger.debug("UID search failed, falling back to sequence SEARCH", exc_info=True)

	# Fallback: sequence-based SEARCH (keep backwards compatibility).
	if not used_uid:
		typ, data = imap.search(None, "SINCE", crit)
		if typ != "OK":
			return []
		uids = data[0].split() if data and data[0] else []
		decoded = [uid.decode() for uid in uids]
		logger.debug("Sequence search returned %d ids (sample: %s)", len(decoded), decoded[:5])

	# If there are no ids, return early
	if not decoded:
		return []

	# Try to fetch INTERNALDATE for each id (use UID or sequence fetch depending on search type)
	# We'll batch the fetch to avoid overly long command strings.
	filtered = []
	excluded = []
	BATCH_INTERNAL_FETCH = 200
	for i in range(0, len(decoded), BATCH_INTERNAL_FETCH):
		batch = decoded[i:i+BATCH_INTERNAL_FETCH]
		seq = ",".join(batch)
		try:
			if used_uid:
				typ2, data2 = imap.uid('fetch', seq, '(INTERNALDATE)')
			else:
				typ2, data2 = imap.fetch(seq, '(INTERNALDATE)')
			if typ2 != 'OK' or not data2:
				logger.debug("INTERNALDATE fetch empty or non-OK for seq=%s typ=%s", seq, typ2)
				# If we can't fetch INTERNALDATE, include all batch items as a safe fallback
				filtered.extend(batch)
				continue
		except Exception:
			logger.debug("INTERNALDATE fetch failed for seq=%s", seq, exc_info=True)
			filtered.extend(batch)
			continue

		# Parse fetch response entries
		# data2 may contain tuples like (b'1 (UID 123 INTERNALDATE "17-Nov-2025 10:12:00 +0000")', b'')
		uid_to_dt = {}
		for item in data2:
			if not isinstance(item, tuple):
				continue
			header = item[0].decode(errors='ignore')
			# Extract UID if present
			m_uid = re.search(r"UID\s+(\d+)", header)
			if m_uid:
				cur_id = m_uid.group(1)
			else:
				# Fallback: first token often is the id (sequence or uid depending on fetch)
				try:
					cur_id = header.split()[0]
				except Exception:
					cur_id = None

			# Extract INTERNALDATE
			m_dt = re.search(r'INTERNALDATE\s+"([^"]+)"', header)
			if m_dt and cur_id:
				raw_dt = m_dt.group(1)
				try:
					pt = email.utils.parsedate_tz(raw_dt)
					if pt:
						ts = email.utils.mktime_tz(pt)
						uid_to_dt[cur_id] = datetime.fromtimestamp(ts, tz=timezone.utc)
				except Exception:
					logger.debug("Failed parsing INTERNALDATE '%s' for id=%s", raw_dt, cur_id)

		# Decide inclusion based on since_date
		for id_ in batch:
			dt = uid_to_dt.get(id_)
			if dt:
				if dt >= since_date.astimezone(timezone.utc):
					filtered.append(id_)
				else:
					excluded.append((id_, dt.isoformat()))
			else:
				# No INTERNALDATE available for this id, include it and log
				filtered.append(id_)
				logger.debug("No INTERNALDATE for id=%s; included by fallback", id_)

	if excluded:
		logger.info("Excluded %d ids older than since_date (sample: %s)", len(excluded), excluded[:5])

	return filtered


def fetch_batch(imap, uids):
	if not uids:
		return {}
	seq = ",".join(uids)
	try:
		typ, data = imap.uid('fetch', seq, '(RFC822 FLAGS)')
		if typ != "OK" or not data:
			logger.warning("Empty fetch response for seq=%s (typ=%s)", seq, typ)
			return {}
	except Exception:
		logger.exception("UID fetch failed for seq=%s", seq)
		return {}

	out = {}
	for item in data:
		if not isinstance(item, tuple):
			continue
		header = item[0].decode(errors="ignore")
		# Try to extract UID from the response (e.g. '... UID 395 ...')
		m = re.search(r"UID\s+(\d+)", header)
		if m:
			cur_uid = m.group(1)
		else:
			# Fallback: first token is often the id we requested
			try:
				cur_uid = header.split()[0]
			except Exception:
				cur_uid = None

		# Extract FLAGS if present
		cur_flags = []
		if "FLAGS (" in header:
			try:
				flags_part = header.split("FLAGS (",1)[1].split(")",1)[0]
				cur_flags = flags_part.split()
			except Exception:
				cur_flags = []

		raw = item[1]
		if cur_uid:
			out[cur_uid] = {"raw": raw, "flags": cur_flags[:]}
		else:
			logger.debug("Could not determine UID for fetch item header: %s", header[:200])

	return out

# --- Notion: inserimento email ---
def create_email_page(msgid, sender, subject, dt, text):
	props = {
		"Message-ID": {"rich_text":[{"type":"text","text":{"content": msgid}}]} if msgid else {"rich_text":[]},
		"From": {"rich_text":[{"type":"text","text":{"content": sender}}]} if sender else {"rich_text":[]},
		"Subject": {"title":[{"type":"text","text":{"content": subject}}]},
		"Body": {"rich_text":[{"type":"text","text":{"content": text}}]} if text else {"rich_text":[]},
		"Email Date": {"date":{"start": dt.astimezone(timezone.utc).isoformat()}},
	}
	try:
		logger.debug("Creating Notion page for Message-ID=%s Subject=%s", (msgid or "" )[:80], (subject or "")[:80])
		page = notion.pages.create(parent={"database_id": LINE_DB_ID}, properties=props)
		logger.info("Notion page created: %s", page.get("id") if isinstance(page, dict) else "(unknown)")
	except Exception:
		logger.exception("Failed to create Notion page for Message-ID=%s", msgid)

# --- Parse headers minimi ---
def parse_email_metadata(raw_bytes):
	m = email.message_from_bytes(raw_bytes)
	def get_header(k):
		v = email.header.decode_header(m.get(k, "")); s = ""
		for part, enc in v:
			s += (part.decode(enc or "utf-8","replace") if isinstance(part, bytes) else part)
		return s.strip()
	msgid = get_header("Message-ID") or ""
	sender = get_header("From") or ""
	subject = get_header("Subject") or ""
	date_tuple = email.utils.parsedate_tz(m.get("Date"))
	dt = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple), tz=timezone.utc) if date_tuple else datetime.now(timezone.utc)
	text, _ = get_best_body(m)
	logger.debug("Parsed email headers: Message-ID=%s From=%s Subject=%s Date=%s", (msgid or "")[:80], (sender or "")[:80], (subject or "")[:80], dt.isoformat())
	return msgid, sender, subject, dt, text

# --- Main ---
def main():
	logger.info("Starting imap-notion-sync (continuous mode: poll interval=%ss)", POLL_INTERVAL)
	context = ssl.create_default_context()

	# Load processed store (keeps track of seen Message-IDs and UIDs to avoid duplicates)
	store = load_store(PROCESSED_STORE_PATH)
	logger.debug("Loaded processed store from %s: folders=%d msgids=%d", PROCESSED_STORE_PATH, len(store.get("folders", {})), len(store.get("msgids", [])))

	# Initialize last sync timestamps per folder (first run: SYNC_SINCE_DAYS back)
	last_sync = {}
	now = datetime.now(timezone.utc)
	initial_since = (now - timedelta(days=SINCE_DAYS)).astimezone(timezone.utc)
	for f in FOLDERS:
		last_sync[f] = initial_since
  
	# print the last_sync dict 
	logger.info("Initial Last Sync timestamps per folder: %s", {k: v.isoformat() for k,v in last_sync.items()})

	while True:
		try:
			logger.info("Connecting to IMAP %s:%s", IMAP_HOST, IMAP_PORT)
			with IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context) as imap:
				imap.login(IMAP_USER, IMAP_PASSWORD)
				logger.info("IMAP login successful for user %s", IMAP_USER)

				for folder in FOLDERS:
					since_date = last_sync.get(folder, initial_since)
					uids = imap_search_since(imap, folder, since_date)
					logger.info("Folder '%s' has %d messages since %s", folder, len(uids), since_date.date().isoformat())

					for i in range(0, len(uids), BATCH_SIZE):
						batch = uids[i:i+BATCH_SIZE]
						logger.info("Processing batch %d: %d messages", (i // BATCH_SIZE) + 1, len(batch))
						results = fetch_batch(imap, batch)
						for uid in batch:
							item = results.get(uid)
							if not item:
								logger.warning("No data for uid %s (skipping)", uid)
								continue
							try:
								msgid, sender, subject, dt, text = parse_email_metadata(item["raw"])
								# Dedup: skip if we've already processed this Message-ID or UID
								if is_seen(store, uid, msgid, folder):
									logger.info("Skipping already-processed message uid=%s msgid=%s", uid, (msgid or "")[:80])
									continue
								if text:
									logger.debug("Creating page for Message-ID=%s", (msgid or "")[:80])
									create_email_page(msgid, sender, subject, dt, text)
									# mark as processed and persist
									try:
										mark_seen(store, uid, msgid, folder)
										save_store(PROCESSED_STORE_PATH, store)
									except Exception:
										logger.exception("Failed marking message seen for uid=%s", uid)
									time.sleep(0.1)  # rate-limit Notion
							except Exception:
								logger.exception("Failed processing uid %s", uid)

					# update last sync timestamp for the folder to now
					last_sync[folder] = datetime.now(timezone.utc)

				try:
					imap.logout()
					logger.info("IMAP logout complete")
				except Exception:
					logger.debug("Error during IMAP logout (continuing)")

		except Exception:
			logger.exception("Unhandled exception during IMAP poll cycle - will retry after sleep")

		logger.info("Last Sync timestamps per folder: %s", {k: v.isoformat() for k,v in last_sync.items()})
		# Sleep before next poll (keeps container alive)
		logger.info("Sleeping %s seconds before next poll", POLL_INTERVAL)
		time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
	main()