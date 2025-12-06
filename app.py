# app.py
import os, ssl, time, email, re, json
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

notion = Client(auth=NOTION_TOKEN)

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

# --- Parser line items stile "Articoli in questa spedizione" ---
RE_ORDER_ID = re.compile(r"\bOrdine\s+([A-Z0-9\-]+)", re.I)
RE_TRACKING = re.compile(r"(?:tracking|numero di tracking)[: ]+\s*([A-Z0-9\-]+)", re.I)
RE_QTY = re.compile(r"\b(\d+)\s+di\s+\d+\b", re.I)

def parse_lineitems(text: str) -> dict:
	items = []
	order_id = None
	tracking = None

	m = RE_ORDER_ID.search(text)
	if m: order_id = m.group(1).strip()
	m = RE_TRACKING.search(text)
	if m: tracking = m.group(1).strip()

	start = text.lower().find("articoli in questa spedizione")
	segment = text[start:] if start >= 0 else text

	chunks = re.split(r"(?:\n|\s){2,}|-{3,}", segment)
	def clean(s): return " ".join(s.strip().split())

	i = 0
	while i < len(chunks):
		t = clean(chunks[i])
		if t and (("×" in t) or (len(t) > 12 and not RE_QTY.search(t))):
			title = t.replace("×", "x")
			qty = None
			variant = None
			sku = None

			for j in range(1,4):
				if i + j >= len(chunks): break
				line = clean(chunks[i+j])
				if not line: continue
				if qty is None:
					mq = RE_QTY.search(line)
					if mq:
						qty = int(mq.group(1))
						continue
				if variant is None and ("/" in line or re.search(r"\b(kg|ml|mm|cm|colore)\b", line, re.I)):
					variant = line
					continue
				if sku is None and (len(line) <= 12 and line.isalnum()):
					sku = line

			if qty is not None:
				items.append({
					"title": title,
					"qty": qty,
					"variant": variant,
					"sku": sku
				})
			i += 3
		else:
			i += 1

	return {"items": items, "order_id": order_id, "tracking": tracking}

# --- IMAP ---
def imap_search_since(imap, folder, since_date):
	typ, _ = imap.select(f'"{folder}"', readonly=True)
	if typ != "OK":
		return []
	crit = since_date.strftime("%d-%b-%Y")
	typ, data = imap.search(None, "SINCE", crit)
	if typ != "OK":
		return []
	uids = data[0].split() if data and data[0] else []
	return [uid.decode() for uid in uids]

def fetch_batch(imap, uids):
	if not uids: return {}
	seq = ",".join(uids)
	typ, data = imap.fetch(seq, "(RFC822 FLAGS UID)")
	if typ != "OK" or not data: return {}
	out = {}
	cur_uid = None; cur_flags = []
	for item in data:
		if not isinstance(item, tuple):
			continue
		header = item[0].decode(errors="ignore")
		if "UID " in header:
			try:
				cur_uid = header.split("UID ")[1].split()[0]
			except Exception:
				cur_uid = None
		if b"FLAGS" in item[0]:
			try:
				flags_part = header.split("FLAGS (",1)[1].split(")",1)[0]
				cur_flags = flags_part.split()
			except Exception:
				cur_flags = []
		raw = item[1]
		if cur_uid:
			out[cur_uid] = {"raw": raw, "flags": cur_flags[:] }
	return out

# --- Notion: upsert solo materiali ---
def find_line_item_page(msgid, title, variant, sku):
	cond = [
		{"property":"Message-ID","rich_text":{"equals": msgid}},
		{"property":"Material","title":{"equals": title}},
	]
	if variant:
		cond.append({"property":"Variant","text":{"equals": variant}})
	if sku:
		cond.append({"property":"SKU","text":{"equals": sku}})
	resp = notion.databases.query(database_id=LINE_DB_ID, filter={"and": cond}, page_size=1)
	return resp["results"][0] if resp["results"] else None

def upsert_items_only(msgid, dt, text):
	parsed = parse_lineitems(text)
	order_id = parsed.get("order_id") or ""
	tracking = parsed.get("tracking") or ""
	for it in parsed["items"]:
		title = it.get("title") or "(Materiale)"
		qty = int(it.get("qty") or 0)
		variant = it.get("variant") or ""
		sku = it.get("sku") or ""
		page = find_line_item_page(msgid, title, variant, sku)
		props = {
			"Material": {"title":[{"type":"text","text":{"content": title}}]},
			"Qty": {"number": qty},
			"Variant": {"rich_text":[{"type":"text","text":{"content": variant}}]} if variant else {"rich_text":[]},
			"SKU": {"rich_text":[{"type":"text","text":{"content": sku}}]} if sku else {"rich_text":[]},
			"Order ID": {"rich_text":[{"type":"text","text":{"content": order_id}}]} if order_id else {"rich_text":[]},
			"Tracking": {"rich_text":[{"type":"text","text":{"content": tracking}}]} if tracking else {"rich_text":[]},
			"Message-ID": {"rich_text":[{"type":"text","text":{"content": msgid}}]} if msgid else {"rich_text":[]},
			"Email Date": {"date":{"start": dt.astimezone(timezone.utc).isoformat()}},
		}
		if page:
			notion.pages.update(page_id=page["id"], properties=props)
		else:
			notion.pages.create(parent={"database_id": LINE_DB_ID}, properties=props)

# --- Parse headers minimi ---
def parse_email_metadata(raw_bytes):
	m = email.message_from_bytes(raw_bytes)
	def get_header(k):
		v = email.header.decode_header(m.get(k, "")); s = ""
		for part, enc in v:
			s += (part.decode(enc or "utf-8","replace") if isinstance(part, bytes) else part)
		return s.strip()
	msgid = get_header("Message-ID") or ""
	date_tuple = email.utils.parsedate_tz(m.get("Date"))
	dt = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple), tz=timezone.utc) if date_tuple else datetime.now(timezone.utc)
	text, _ = get_best_body(m)
	return msgid, dt, text

# --- Main ---
def main():
	context = ssl.create_default_context()
	since_date = (datetime.now(timezone.utc) - timedelta(days=SINCE_DAYS)).astimezone(timezone.utc)
	with IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context) as imap:
		imap.login(IMAP_USER, IMAP_PASSWORD)
		for folder in FOLDERS:
			uids = imap_search_since(imap, folder, since_date)
			for i in range(0, len(uids), BATCH_SIZE):
				batch = uids[i:i+BATCH_SIZE]
				results = fetch_batch(imap, batch)
				for uid in batch:
					item = results.get(uid)
					if not item:
						continue
					msgid, dt, text = parse_email_metadata(item["raw"])
					if text:
						upsert_items_only(msgid, dt, text)
						time.sleep(0.1)  # rate-limit Notion
		imap.logout()

if __name__ == "__main__":
	main()