import os, sys, requests, csv
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

# 1. Read token from env
GITHUB_TOKEN = os.getenv("GH_TOKEN")
if not GITHUB_TOKEN:
    print("Error: GH_TOKEN environment variable not set.", file=sys.stderr)
    sys.exit(1)

# 2. Load plugin list
repos = []
with open("plugin-repos.txt", encoding="utf-8-sig") as f:
    for line in f:
        url = line.strip()
        parts = url.rstrip("/").split("/")[-2:]
        if len(parts) == 2:
            repos.append(tuple(parts))
        else:
            print(f"Skipping invalid URL: {url}", file=sys.stderr)

# 3. GraphQL endpoint & headers
GQL_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json"
}
TAG_PATTERNS = {
    "productivity":"productivity","task":"productivity","todo":"productivity",
    "kanban":"productivity","theme":"theme","css":"theme","dark":"theme",
    "appearance":"theme","calendar":"note-taking","journal":"note-taking",
    "note":"note-taking","markdown":"note-taking","sync":"integration",
    "api":"integration","integration":"integration"
}
def infer_tags(desc):
    d = (desc or "").lower(); tags = {v for k,v in TAG_PATTERNS.items() if k in d}
    return ";".join(sorted(tags)) or "other"

def batch_query(batch):
    qs = []
    for i,(owner,name) in enumerate(batch):
        alias = f"r{i}"
        qs.append(f'''
            {alias}: repository(owner: "{owner}", name: "{name}") {{
                name stargazerCount description owner {{ login }}
                repositoryTopics(first: 5) {{ nodes {{ topic {{ name }} }} }}
            }}
        ''')
    return {"query": "{ " + " ".join(qs) + " }"}

# 4. Prepare output CSV
today = date.today().strftime("%Y%m%d")
out_file = f"plugin-details-{today}.csv"
fields = ["name","owner","stars","status","description","topics","tags"]
with open(out_file, "w", newline="", encoding="utf-8") as csvf:
    writer = csv.DictWriter(csvf, fieldnames=fields)
    writer.writeheader()

    # 5. Fetch in batches
    for i in range(0, len(repos), 40):
        batch = repos[i:i+40]
        payload = batch_query(batch)
        resp = requests.post(GQL_URL, json=payload, headers=HEADERS)
        code = resp.status_code
        data = resp.json().get("data", {}) if code==200 else {}
        for idx,(owner,name) in enumerate(batch):
            alias = f"r{idx}"
            rd = data.get(alias)
            if rd:
                topics = [n["topic"]["name"] for n in rd["repositoryTopics"]["nodes"]]
                desc   = rd.get("description") or ""
                writer.writerow({
                    "name": rd["name"],
                    "owner": rd["owner"]["login"],
                    "stars": rd["stargazerCount"],
                    "status": 200,
                    "description": desc,
                    "topics": ";".join(topics),
                    "tags": infer_tags(desc)
                })
            else:
                writer.writerow({
                    "name": name,"owner": owner,"stars": 0,
                    "status": code if code!=200 else 404,
                    "description": "","topics":"","tags":"other"
                })
print(f"Done. See {out_file}")
