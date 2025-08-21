import json

with open("data/fda_additive_dict.json") as f:
    additives = json.load(f)

token = "CARAMEL COLOR"
token_norm = token.strip().lower()

found = None
for name, data in additives.items():
    if token_norm == name.lower() or token_norm in [a.lower() for a in data.get("aliases", [])]:
        found = name
        break

print("Matched:", found)
