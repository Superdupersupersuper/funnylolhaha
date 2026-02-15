#!/usr/bin/env python3
"""
Finalize setup: Add DATABASE_URL as a Render database reference
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

print("🔗 Linking database to service using Render's built-in connection...")

# Get current service config
service_response = requests.get(f"{BASE_URL}/services/{SERVICE_ID}", headers=get_headers())
if not service_response.ok:
    print(f"❌ Failed to get service")
    exit(1)

service = service_response.json()
current_envvars = service.get("service", {}).get("serviceDetails", {}).get("envVars", [])

# Add DATABASE_URL using Render's fromDatabase reference
# This is the correct way to link a database in Render
updated_envvars = [ev for ev in current_envvars if ev.get("key") != "DATABASE_URL"]
updated_envvars.append({
    "key": "DATABASE_URL",
    "fromDatabase": {
        "id": DB_ID,
        "property": "connectionString"  # Render will populate this automatically
    }
})

print("📝 Adding DATABASE_URL environment variable...")

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
    print("✅ DATABASE_URL linked successfully!")
    
    # Trigger deploy
    print("\n🚀 Triggering first deployment...")
    deploy_response = requests.post(
        f"{BASE_URL}/services/{SERVICE_ID}/deploys",
        headers=get_headers()
    )
    
    if deploy_response.ok:
        deploy = deploy_response.json()
        deploy_id = deploy.get("deploy", {}).get("id")
        print(f"✅ Deployment started!")
        print(f"   Deploy ID: {deploy_id}")
        print(f"\n⏳ This will take 3-5 minutes. Monitor progress:")
        print(f"   python3 render_cli.py status")
        print(f"   python3 render_cli.py logs")
        print(f"\n🔗 Once complete, your app will be at:")
        print(f"   https://mention-markets-web.onrender.com")
        print(f"\n📝 Next steps after deployment:")
        print(f"   1. Visit /admin/login")
        print(f"   2. Change ADMIN_PASSWORD (default: changeme-admin-2024)")
        print(f"   3. Upload your first transcript!")
    else:
        print(f"⚠️  Failed to trigger deploy: {deploy_response.status_code}")
        print(deploy_response.text)
else:
    print(f"❌ Failed to link database: {update_response.status_code}")
    print(update_response.text)

