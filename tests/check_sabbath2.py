import sys
# fake import paths
sys.path.insert(0, "./src")
from tradebot_sci.config.loader import load_settings
from tradebot_sci.config.profile_loader import load_profile_settings
from tradebot_sci.runtime.sabbath import SabbathContext
from datetime import datetime, timezone

settings = load_settings()
profile_settings = load_profile_settings(settings.app.profile_name)

ctx = SabbathContext(profile_settings)
sabbath_active, next_sabbath, last_sabbath = ctx.evaluate(datetime.now(timezone.utc))
print(f"\n---> SABBATH ACTIVE: {sabbath_active}\n")
