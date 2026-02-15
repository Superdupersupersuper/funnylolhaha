#!/usr/bin/env python3
"""
Create Postgres database and link it to the web service
"""
import requests
import json
import time

API_KEY = "rnd_XToSneCSEQP0QdaeAYQTtlZWCNzy"
BASE_URL = "https://api.render.com/v1"

def get_headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def create_database():
    """Create a PostgreSQL database"""
    
    # Get owner ID
    owners_response = requests.get(f"{BASE_URL}/owners", headers=get_headers())
    if not owners_response.ok:
        print(f"❌ Failed to get owner")
        return None
    
    owner_id = owners_response.json()[0]["owner"]["id"]
    
    db_config = {
        "name": "mention-markets-db",
        "ownerId": owner_id,
        "plan": "free",
        "region": "oregon",
        "databaseName": "mention_markets",
        "databaseUser": "mention_markets_user",
        "version": "16"  # PostgreSQL 16
    }
    
    print("\n📊 Creating PostgreSQL database...")
    print(f"   Name: mention-markets-db")
    print(f"   Plan: free")
    
    response = requests.post(
        f"{BASE_URL}/postgres",
        headers=get_headers(),
        data=json.dumps(db_config)
    )
    
    if response.ok:
        db = response.json()
        db_id = db.get("id")
        print(f"\n✅ Database created!")
        print(f"   ID: {db_id}")
        print(f"   Status: Provisioning...")
        print(f"\n⏳ Waiting for database to be ready (this takes ~2 minutes)...")
        
        # Wait for database to be ready
        for i in range(60):
            time.sleep(5)
            db_response = requests.get(f"{BASE_URL}/postgres/{db_id}", headers=get_headers())
            if db_response.ok:
                db_data = db_response.json()
                status = db_data.get("status")
                print(f"   Status: {status} {'.' * ((i % 3) + 1)}")
                
                if status == "available":
                    print(f"\n✅ Database is ready!")
                    # Try different possible fields for connection string
                    internal_url = (
                        db_data.get("connectionInfo", {}).get("internalConnectionString") or
                        db_data.get("internalConnectionString") or
                        db_data.get("connectionString")
                    )
                    if internal_url:
                        print(f"   Internal URL: {internal_url[:60]}...")
                    else:
                        print(f"   ⚠️  Connection string not yet available")
                        print(f"   Full response: {json.dumps(db_data, indent=2)}")
                    return {
                        "id": db_id,
                        "internal_url": internal_url
                    }
        
        print(f"\n⚠️  Database is still provisioning. Check dashboard in a few minutes.")
        return {"id": db_id, "internal_url": None}
    else:
        print(f"\n❌ Failed to create database: {response.status_code}")
        print(response.text)
        return None

def update_service_env(service_id, database_url):
    """Add DATABASE_URL to the web service"""
    
    print(f"\n📝 Adding DATABASE_URL to service...")
    
    # Get current env vars
    service_response = requests.get(f"{BASE_URL}/services/{service_id}", headers=get_headers())
    if not service_response.ok:
        print(f"❌ Failed to get service")
        return False
    
    service = service_response.json()
    current_envvars = service.get("service", {}).get("serviceDetails", {}).get("envVars", [])
    
    # Add DATABASE_URL
    updated_envvars = [ev for ev in current_envvars if ev.get("key") != "DATABASE_URL"]
    updated_envvars.append({
        "key": "DATABASE_URL",
        "value": database_url
    })
    
    # Update service
    update_response = requests.patch(
        f"{BASE_URL}/services/{service_id}",
        headers=get_headers(),
        data=json.dumps({
            "serviceDetails": {
                "envVars": updated_envvars
            }
        })
    )
    
    if update_response.ok:
        print(f"✅ DATABASE_URL added!")
        print(f"\n🚀 Triggering first deployment...")
        
        # Trigger deploy
        deploy_response = requests.post(
            f"{BASE_URL}/services/{service_id}/deploys",
            headers=get_headers()
        )
        
        if deploy_response.ok:
            print(f"✅ Deployment started!")
            print(f"\n📊 Check status with: python3 render_cli.py status")
            print(f"📜 Watch logs with: python3 render_cli.py logs")
            return True
        else:
            print(f"⚠️  Deploy trigger failed: {deploy_response.status_code}")
            return False
    else:
        print(f"❌ Failed to update service: {update_response.status_code}")
        print(update_response.text)
        return False

def main():
    # Create database
    db_info = create_database()
    if not db_info or not db_info.get("internal_url"):
        print("\n⚠️  Database created but not ready yet.")
        print("   Run this script again in 2 minutes, or")
        print("   manually add DATABASE_URL from Render dashboard")
        return
    
    # Update service with DATABASE_URL
    service_id = "srv-d693pammcj7s738j4bng"  # From previous step
    update_service_env(service_id, db_info["internal_url"])

if __name__ == "__main__":
    main()

