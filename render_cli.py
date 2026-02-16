#!/usr/bin/env python3
"""
Render CLI Helper - Check deployment status and logs
Usage: python3 render_cli.py [command]

Commands:
  status              - Show all services and their status
  logs                - Show recent deployment logs
  deploy              - Trigger a new deployment
  health              - Check if services are healthy
  configure_web_prisma - Set env vars + build/start commands for Prisma DB init
"""

import os
import requests
import sys
import json
from datetime import datetime

# Your Render API key (env var takes precedence)
API_KEY = os.environ.get("RENDER_API_KEY", "rnd_XToSneCSEQP0QdaeAYQTtlZWCNzy")
BASE_URL = "https://api.render.com/v1"

WEB_SERVICE_ID = "srv-d694bsjuibrs739aiib0"
DB_ID = "dpg-d693piogjchc73dflltg-a"

def get_headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }

def list_services():
    """List all services"""
    print("\n📊 Fetching Render services...")
    try:
        response = requests.get(f"{BASE_URL}/services", headers=get_headers())
        response.raise_for_status()
        data = response.json()
        
        print(f"\n✅ Found {len(data)} service(s):\n")
        for service in data:
            service_id = service.get('service', {}).get('id', 'N/A')
            name = service.get('service', {}).get('name', 'Unknown')
            service_type = service.get('service', {}).get('type', 'Unknown')
            status = service.get('service', {}).get('suspended', 'Unknown')
            
            # Get detailed service info
            detail_response = requests.get(f"{BASE_URL}/services/{service_id}", headers=get_headers())
            if detail_response.ok:
                detail = detail_response.json()
                deploy_status = "🟢 Live"
                latest_deploy = "No deploys yet"
                
                print(f"📦 {name}")
                print(f"   ID: {service_id}")
                print(f"   Type: {service_type}")
                print(f"   Status: {deploy_status}")
                print(f"   Suspended: {'Yes ⚠️' if status == 'suspended' else 'No ✅'}")
                
                # Try to get latest deploy
                deploys_response = requests.get(
                    f"{BASE_URL}/services/{service_id}/deploys",
                    headers=get_headers(),
                    params={"limit": 1}
                )
                if deploys_response.ok:
                    deploys = deploys_response.json()
                    if deploys:
                        latest = deploys[0].get('deploy', {})
                        deploy_status = latest.get('status', 'unknown')
                        created = latest.get('createdAt', '')
                        commit = latest.get('commit', {}).get('message', 'N/A')[:50]
                        
                        status_emoji = {
                            'live': '🟢',
                            'building': '🟡', 
                            'failed': '🔴',
                            'canceled': '⚪'
                        }.get(deploy_status, '❓')
                        
                        print(f"   Latest Deploy: {status_emoji} {deploy_status}")
                        print(f"   Commit: {commit}")
                        print(f"   Time: {created}")
                
                print()
            
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        return None

def get_latest_logs(service_id=None):
    """Get latest deployment logs"""
    print("\n📜 Fetching deployment logs...")
    
    # If no service_id provided, get first service
    if not service_id:
        services_response = requests.get(f"{BASE_URL}/services", headers=get_headers())
        if services_response.ok:
            services = services_response.json()
            if services:
                service_id = services[0].get('service', {}).get('id')
                print(f"Using service: {services[0].get('service', {}).get('name')}")
    
    if not service_id:
        print("❌ No service found")
        return
    
    try:
        # Get latest deploy
        deploys_response = requests.get(
            f"{BASE_URL}/services/{service_id}/deploys",
            headers=get_headers(),
            params={"limit": 1}
        )
        deploys_response.raise_for_status()
        deploys = deploys_response.json()
        
        if not deploys:
            print("❌ No deploys found")
            return
        
        latest_deploy = deploys[0].get('deploy', {})
        deploy_id = latest_deploy.get('id')
        status = latest_deploy.get('status')
        commit_msg = latest_deploy.get('commit', {}).get('message', 'N/A')
        
        print(f"\n📋 Latest Deploy:")
        print(f"   Status: {status}")
        print(f"   Commit: {commit_msg}")
        print(f"   Deploy ID: {deploy_id}\n")
        
        # Get logs for this deploy
        logs_response = requests.get(
            f"{BASE_URL}/services/{service_id}/deploys/{deploy_id}/logs",
            headers=get_headers()
        )
        
        if logs_response.ok:
            logs = logs_response.json()
            print("📝 Recent logs:")
            print("="*80)
            for log_entry in logs[-50:]:  # Last 50 entries
                timestamp = log_entry.get('timestamp', '')
                message = log_entry.get('message', '')
                print(f"{timestamp} | {message}")
            print("="*80)
        else:
            print(f"⚠️ Could not fetch logs: {logs_response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")

def trigger_deploy(service_id=None):
    """Trigger a new deployment"""
    print("\n🚀 Triggering new deployment...")
    
    # If no service_id provided, get first service
    if not service_id:
        services_response = requests.get(f"{BASE_URL}/services", headers=get_headers())
        if services_response.ok:
            services = services_response.json()
            if services:
                service_id = services[0].get('service', {}).get('id')
                print(f"Using service: {services[0].get('service', {}).get('name')}")
    
    if not service_id:
        print("❌ No service found")
        return
    
    try:
        response = requests.post(
            f"{BASE_URL}/services/{service_id}/deploys",
            headers=get_headers()
        )
        response.raise_for_status()
        deploy = response.json()
        
        print(f"✅ Deployment triggered!")
        print(f"   Deploy ID: {deploy.get('deploy', {}).get('id')}")
        print(f"   Status: {deploy.get('deploy', {}).get('status')}")
        print("\n💡 Run 'python3 render_cli.py logs' to watch progress")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")

def configure_web_prisma():
    """Configure the web service for Prisma DB initialization.

    - Fetches the internal DATABASE_URL from the Render Postgres instance.
    - Sets DATABASE_URL, NODE_ENV, ADMIN_PASSWORD, ADMIN_SESSION_SECRET on the
      web service (upsert).
    - Patches the build command to ``npm install --include=dev`` so that
      devDependencies (prisma, typescript, tailwindcss …) are available even
      when NODE_ENV=production.
    - Ensures the start command runs ``npx prisma db push`` before ``npm start``.
    - Triggers a redeploy so the changes take effect immediately.
    """
    headers = {**get_headers(), "Content-Type": "application/json"}

    # --- 1) Fetch internal DB connection string ---
    print("\n🔗 Fetching Postgres connection info …")
    r = requests.get(f"{BASE_URL}/postgres/{DB_ID}/connection-info", headers=headers)
    r.raise_for_status()
    internal_url = r.json()["internalConnectionString"]
    print(f"   Internal URL: {internal_url[:50]}…")

    # --- 2) Read current service config ---
    print("\n📦 Reading current service config …")
    r = requests.get(f"{BASE_URL}/services/{WEB_SERVICE_ID}", headers=headers)
    r.raise_for_status()
    svc = r.json()
    details = svc.get("serviceDetails", {}).get("envSpecificDetails", {})
    print(f"   rootDir:      {svc.get('rootDir')}")
    print(f"   buildCommand: {details.get('buildCommand')}")
    print(f"   startCommand: {details.get('startCommand')}")

    # --- 3) Upsert environment variables ---
    print("\n🔑 Setting environment variables …")
    env_vars = [
        {"key": "DATABASE_URL", "value": internal_url},
        {"key": "NODE_ENV", "value": "production"},
        {"key": "ADMIN_PASSWORD", "value": "changeme-admin-2024"},
        {"key": "ADMIN_SESSION_SECRET",
         "value": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4"},
    ]
    for ev in env_vars:
        r2 = requests.put(
            f"{BASE_URL}/services/{WEB_SERVICE_ID}/env-vars/{ev['key']}",
            headers=headers,
            data=json.dumps({"value": ev["value"]}),
        )
        tag = "✅" if r2.ok else f"❌ {r2.status_code}"
        print(f"   {tag} {ev['key']}")

    # --- 4) Patch build + start commands ---
    desired_build = "npm install --include=dev && npx prisma generate && npm run build"
    desired_start = "npx prisma db push --accept-data-loss --skip-generate && npm start"

    if details.get("buildCommand") != desired_build or details.get("startCommand") != desired_start:
        print("\n⚙️  Patching build/start commands …")
        r3 = requests.patch(
            f"{BASE_URL}/services/{WEB_SERVICE_ID}",
            headers=headers,
            data=json.dumps({
                "serviceDetails": {
                    "envSpecificDetails": {
                        "buildCommand": desired_build,
                        "startCommand": desired_start,
                    }
                }
            }),
        )
        r3.raise_for_status()
        new_details = r3.json().get("serviceDetails", {}).get("envSpecificDetails", {})
        print(f"   buildCommand: {new_details.get('buildCommand')}")
        print(f"   startCommand: {new_details.get('startCommand')}")
    else:
        print("\n⚙️  Build/start commands already correct — skipping patch.")

    # --- 5) Trigger redeploy ---
    print("\n🚀 Triggering redeploy …")
    r4 = requests.post(
        f"{BASE_URL}/services/{WEB_SERVICE_ID}/deploys",
        headers=headers,
    )
    r4.raise_for_status()
    dep = r4.json().get("deploy", r4.json())
    print(f"   Deploy ID: {dep.get('id')}")
    print(f"   Status:    {dep.get('status')}")
    print("\n💡 Run 'python3 render_cli.py logs' to watch progress")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nQuick check:")
        list_services()
        return
    
    command = sys.argv[1].lower()
    
    if command == "status":
        list_services()
    elif command == "logs":
        get_latest_logs()
    elif command == "deploy":
        trigger_deploy()
    elif command == "health":
        print("\n🏥 Health Check:")
        services = list_services()
        if services:
            print(f"\n✅ Render API is reachable")
            print(f"   Services found: {len(services)}")
    elif command == "configure_web_prisma":
        configure_web_prisma()
    else:
        print(f"❌ Unknown command: {command}")
        print(__doc__)

if __name__ == "__main__":
    main()


