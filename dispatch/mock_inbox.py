from datetime import datetime

received_advisories = []


def add_to_inbox(advisory, dispatch_status):

    entry = {
        "timestamp": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "risk_level": advisory.get(
            "risk_level",
            "unknown"
        ),

        "zones": advisory.get(
            "zones",
            []
        ),

        "advisory_en": advisory.get(
            "advisory_en",
            ""
        ),

        "advisory_ta": advisory.get(
            "advisory_ta",
            ""
        ),

        "confidence_note": advisory.get(
            "confidence_note",
            ""
        ),

        "dispatch_status": dispatch_status
    }

    received_advisories.append(entry)

    return entry


def get_latest():

    if not received_advisories:
        return None

    return received_advisories[-1]
