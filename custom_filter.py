# custom_filter.py - example plugin
# Implement `should_create_page(meta, body) -> bool | dict | None`.
# - Return False or None to skip creating the Notion page
# - Return True to allow creation
# - Return dict to allow property overrides (example included below)

from datetime import datetime
import re
import os


def rule_subject_contains(keyword, meta, body):
    """Return True if subject contains keyword (case-insensitive)."""
    subj = (meta.get("subject") or "").lower()
    return keyword.lower() in subj


def rule_sender_whitelist(whitelist, meta, body):
    """Allow only senders in the whitelist (exact match or domain match).
    whitelist: list of addresses or domains (e.g. ['alerts@example.com', 'trusted.com'])
    """
    sender = (meta.get("from") or "").lower()
    for w in whitelist:
        w = w.lower()
        if w.startswith("@"):
            # domain style: @domain.com
            if sender.endswith(w):
                return True
        elif "@" not in w:
            # domain without @
            if sender.endswith("@" + w):
                return True
        else:
            if sender == w:
                return True
    return False


def rule_regex_subject(pattern, meta, body):
    """Match subject with a regex pattern (case-insensitive)."""
    subj = (meta.get("subject") or "")
    try:
        return bool(re.search(pattern, subj, re.I))
    except re.error:
        return False


def rule_blacklist_domains(domains, meta, body):
    """Skip messages from blacklisted domains."""
    sender = (meta.get("from") or "").lower()
    for d in domains:
        if sender.endswith("@" + d.lower()):
            return False
    return True


def rule_return_props_example(meta, body):
    """Example that returns a dict to instruct wrapper to modify Notion props.
    The wrapper must be updated to consume this dict; shown here as an example.
    Example return value:
      {"create": True, "properties_override": {"Tag": "invoice"}}
    """
    subj = (meta.get("subject") or "").lower()
    if "invoice" in subj:
        return {"create": True, "properties_override": {"Tag": "invoice"}}
    return None


def should_create_page(meta, body):
    """
    Default decision function combining a few example rules.

    You can edit this function or build your own and set the environment
    variable `CUSTOM_FILTER_MODULE` to point to a different module name.

    Examples included in this file:
    - `rule_subject_contains(keyword, meta, body)`
    - `rule_sender_whitelist(whitelist, meta, body)`
    - `rule_regex_subject(pattern, meta, body)`
    - `rule_blacklist_domains(domains, meta, body)`
    - `rule_return_props_example(meta, body)` (returns dict)

    Behavior implemented below:
    - If body contains the marker `NO-SYNC` -> skip
    - If subject contains "invoice" -> create
    - If sender is in whitelist -> create
    - If sender is blacklisted -> skip
    - If subject matches order regex -> create
    - Otherwise create
    """
    try:
        # Quick opt-out marker in body
        if body and "no-sync" in body.lower():
            return False

        # Example: always create invoices
        if rule_subject_contains("invoice", meta, body):
            return True

        # Example whitelist for senders (modify to suit your world)
        whitelist = ["orders@example.com", "spedizioni@brt.it", "trusted.com"]
        if rule_sender_whitelist(whitelist, meta, body):
            return True

        # Example: skip marketing from certain domains
        if not rule_blacklist_domains(["spamdomain.com", "marketing.example"], meta, body):
            return False

        # Example regex: subjects that mention "order #123" style
        if rule_regex_subject(r"order\s+#?\d+", meta, body):
            return True

        # Default: create
        return True
    except Exception:
        # On error, be permissive (don't silently drop messages)
        return True


# --- Examples of usage in this file (not executed):
#
# 1) Simple subject keyword filter (already used above):
#    if rule_subject_contains("invoice", meta, body): ...
#
# 2) Using regex to match order numbers:
#    if rule_regex_subject(r"order\s+#?\d+", meta, body): ...
#
# 3) Returning property overrides (requires wrapper support):
#    return {"create": True, "properties_override": {"Tag": "invoice"}}
#
# 4) Custom behavior based on environment variable:
#    import os
#    mode = os.environ.get('MY_FILTER_MODE')
#    if mode == 'only-invoices':
#        return rule_subject_contains('invoice', meta, body)
