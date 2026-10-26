import re


class NLPService:
    def analyze_report(self, text, incident_type=""):
        text = text.lower()
        incident_type = incident_type.lower()

        categories = {
            "Weapon": [
                "gun", "guns", "knife", "knives", "weapon", "weapons"
            ],
            "Fighting": [
                "fight", "fighting", "attacked", "assault",
                "got hit", "punched", "beaten", "punch", "beat"
            ],
            "Medical Emergency": [
                "injury", "injured", "unconscious",
                "fainted", "medical"
            ],
            "Suspicious Activity": [
                "suspicious", "following", "stalking", "threat"
            ],
            "Fire": [
                "fire", "smoke", "burning", "flames"
            ],
            "Fall": [
                "fell", "fall", "slipped"
            ],
        }

        category = "Other"

        # Check the incident type first
        for name in categories:
            if re.search(
                r"\b" + re.escape(name.lower()) + r"\b",
                incident_type
            ):
                category = name
                break

        # Check the description if no category was found
        if category == "Other":
            for name, keywords in categories.items():
                if any(
                    re.search(
                        r"\b" + re.escape(word) + r"\b",
                        text
                    )
                    for word in keywords
                ):
                    category = name
                    break

        urgent_patterns = [
            r"\bhelp\b",
            r"\bemergency\b",
            r"\bdanger\b",
            r"\burgent\b",
            r"\bbleeding\b",
            r"\bunconscious\b",
            r"\battack\w*\b",
            r"\bassault\w*\b",
            r"\bgun\w*\b",
            r"\bknife\b",
            r"\bknives\b",
            r"\bweapon\w*\b",
        ]

        urgency = (
            "High"
            if any(
                re.search(pattern, text)
                for pattern in urgent_patterns
            )
            else "Normal"
        )

        return {
            "category": category,
            "urgency": urgency,
            "report": text
        }


nlp_service = NLPService()