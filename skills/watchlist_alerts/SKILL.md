---
name: watchlist_alerts
description: The ranked "what changed" signals for the whole team or for one person's focus, team alerts (e.g. alert me when Canary Wharf vacancy goes above 10%), and each person's focus setup.
---
Use for "what should I know this week", "any risks", "what changed". Default to scope "team";
use scope "me" when the person asks about their own markets or "for me".
When someone states a threshold in words, call add_watch_rule with market, metric, operator and
value. An alert belongs to the person who asked and fires in their own view; pass
share_with_team only when they say the whole team should get it.
When someone asks to see more or less of a submarket or topic ("more Fitzrovia, less macro",
"only rents and vacancy", "just the top 3"), call update_focus with their words. This changes only
their own "For you" view.
When someone describes their job or asks to set up their view, call propose_setup, show the
proposal, and call apply_setup only after they confirm.
