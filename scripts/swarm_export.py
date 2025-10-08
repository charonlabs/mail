import json

from rich import print

from mail import MAILSwarmTemplate
from mail.utils.serialize import export

with open("swarms.json", encoding="utf-8") as f:
    swarms = json.load(f)

templates = [MAILSwarmTemplate.from_swarm_json(json.dumps(swarm)) for swarm in swarms]
out = export(templates)
print(json.dumps(json.loads(out), indent=2))
