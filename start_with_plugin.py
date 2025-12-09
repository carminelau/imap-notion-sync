# start_with_plugin.py
# Wrapper to load an optional plugin `custom_filter.py` and monkey-patch
# the `create_email_page` function in the app before starting.

import sys
import importlib
import logging
import traceback

# Ensure /app is on path (the image puts code there)
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("start-with-plugin")

# Try to load plugin module name from env or default to custom_filter
import os
plugin_module = os.environ.get("CUSTOM_FILTER_MODULE", "custom_filter")
cf = None
try:
    cf = importlib.import_module(plugin_module)
    logger.info("Loaded custom filter module: %s", plugin_module)
except ModuleNotFoundError:
    logger.info("No custom filter module '%s' found - running default behavior", plugin_module)
except Exception:
    logger.exception("Error loading custom filter module '%s'", plugin_module)

# Import app from the image
try:
    import app
except Exception:
    logger.exception("Failed to import app module. Ensure the image exposes app.py in /app.")
    raise

orig_create = getattr(app, "create_email_page", None)

def patched_create_email_page(msgid, sender, subject, dt, text):
    try:
        meta = {
            "message_id": msgid,
            "from": sender,
            "subject": subject,
            "date": dt,
        }
        # If plugin provides should_create_page, consult it
        if cf and hasattr(cf, "should_create_page"):
            try:
                decision = cf.should_create_page(meta, text)
            except Exception:
                logger.exception("custom_filter.should_create_page raised an exception; defaulting to create")
                decision = True

            # Interpret decision
            if decision is False or decision is None:
                logger.info("custom_filter prevented creation for Message-ID=%s", (msgid or "")[:80])
                return
            # if True or dict -> continue to create. Dict may be used in future for property overrides.

        # Default: call original create
        if orig_create:
            return orig_create(msgid, sender, subject, dt, text)
        else:
            logger.error("Original create_email_page not found in app module")
    except Exception:
        logger.error("Error in patched_create_email_page:\n%s", traceback.format_exc())
        if orig_create:
            return orig_create(msgid, sender, subject, dt, text)

# Apply monkey patch
app.create_email_page = patched_create_email_page
logger.info("Applied patched create_email_page. Starting app.main()")

if __name__ == "__main__":
    app.main()
