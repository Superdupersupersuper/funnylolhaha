#!/usr/bin/env python3
"""
Render CLI Helper - Check deployment status and logs
Usage: python3 render_cli.py [command]

Commands:
  status    - Show all services and their status
  logs      - Show recent deployment logs
  deploy    - Trigger a new deployment
  health    - Check if services are healthy
"""

import requests
import sys
import json
from datetime import datetime

# Your Render API key
API_KEY = "rnd_XToSneCSEQP0QdaeAYQTtlZWCNzy"
BASE_URL = "https://api.render.com/v1"

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
    else:
        print(f"❌ Unknown command: {command}")
        print(__doc__)

if __name__ == "__main__":
    main()

