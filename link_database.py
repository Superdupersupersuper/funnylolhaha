#!/usr/bin/env python3
"""
Link existing database to web service
"""
import requests
import json

API_KEY = "rnd_XToSneCSEQP0QdaeAYQTtlZWCNzy"
BASE_URL = "https://api.render.com/v1"
SERVICE_ID = "srv-d693pammcj7s738j4bng"
DB_ID = "dpg-d693piogjchc73dflltg-a"

def get_headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

print("📊 Fetching database info...")
db_response = requests.get(f"{BASE_URL}/postgres/{DB_ID}", headers=get_headers())

if not db_response.ok:
    print(f"❌ Failed to get database: {db_response.status_code}")
    exit(1)

db_data = db_response.json()
status = db_data.get("status")
print(f"   Status: {status}")

if status != "available":
    print(f"⏳ Database is still provisioning. Wait a minute and try again.")
    exit(0)

# Get connection string
internal_url = (
    db_data.get("connectionInfo", {}).get("internalConnectionString") or
    db_data.get("internalConnectionString") or
    db_data.get("connectionString")
)

if not internal_url:
    print(f"❌ Connection string not found in database info:")
    print(json.dumps(db_data, indent=2))
    exit(1)

print(f"✅ Connection string retrieved")
print(f"   URL: {internal_url[:60]}...")

# Update service with DATABASE_URL
print(f"\n📝 Adding DATABASE_URL to service...")

service_response = requests.get(f"{BASE_URL}/services/{SERVICE_ID}", headers=get_headers())
if not service_response.ok:
    print(f"❌ Failed to get service")
    exit(1)

service = service_response.json()
current_envvars = service.get("service", {}).get("serviceDetails", {}).get("envVars", [])

# Remove old DATABASE_URL if exists, add new one
updated_envvars = [ev for ev in current_envvars if ev.get("key") != "DATABASE_URL"]
updated_envvars.append({
    "key": "DATABASE_URL",
    "value": internal_url
})

update_response = requests.patch(
    f"{BASE_URL}/services/{SERVICE_ID}",
    headers=get_headers(),
    data=json.dumps({
        "serviceDetails": {
            "envVars": updated_envvars
        }
    })
)

if update_response.ok:
    print(f"✅ DATABASE_URL added to service!")
    
    # Trigger deploy
    print(f"\n🚀 Triggering deployment...")
    deploy_response = requests.post(
        f"{BASE_URL}/services/{SERVICE_ID}/deploys",
        headers=get_headers()
    )
    
    if deploy_response.ok:
        deploy = deploy_response.json()
        deploy_id = deploy.get("deploy", {}).get("id")
        print(f"✅ Deployment started!")
        print(f"   Deploy ID: {deploy_id}")
        print(f"\n📊 Check status: python3 render_cli.py status")
        print(f"📜 Watch logs: python3 render_cli.py logs")
        print(f"\n🔗 Your app will be live at:")
        print(f"   https://mention-markets-web.onrender.com")
    else:
        print(f"⚠️  Failed to trigger deploy: {deploy_response.status_code}")
else:
    print(f"❌ Failed to update service: {update_response.status_code}")
    print(update_response.text)

