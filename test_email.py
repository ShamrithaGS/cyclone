import json
from dispatch.email_dispatch import dispatch_advisory, send_email

with open(
    "mock/advisory.json",
    "r",
    encoding="utf-8"
) as f:
    advisory = json.load(f)

result = dispatch_advisory(advisory)

print(result)

