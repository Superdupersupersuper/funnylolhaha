#!/usr/bin/env python3
"""
Create a new Render web service for the Next.js app
"""
import requests
import json
import secrets

API_KEY = "rnd_XToSneCSEQP0QdaeAYQTtlZWCNzy"
BASE_URL = "https://api.render.com/v1"

def get_headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def create_web_service():
    """Create a new web service for the Next.js app"""
    
    # First, get the owner ID
    print("📋 Fetching account info...")
    owners_response = requests.get(f"{BASE_URL}/owners", headers=get_headers())
    if not owners_response.ok:
        print(f"❌ Failed to get account info: {owners_response.status_code}")
        return
    
    owners = owners_response.json()
    if not owners:
        print("❌ No owner found")
        return
    
    owner_id = owners[0]["owner"]["id"]
    print(f"✅ Owner ID: {owner_id}")
    
    # Generate session secret
    session_secret = secrets.token_hex(32)
    
    # Correct Render API format with envSpecificDetails
    service_config = {
        "type": "web_service",
        "name": "mention-markets-web",
        "ownerId": owner_id,
        "repo": "https://github.com/Superdupersupersuper/funnylolhaha",
        "branch": "main",
        "rootDir": "web",
        "autoDeploy": "yes",
        "serviceDetails": {
            "env": "node",
            "buildCommand": "npm install && npx prisma generate && npm run build",
            "startCommand": "npx prisma migrate deploy && npm start",
            "healthCheckPath": "/",
            "pullRequestPreviewsEnabled": "no",
            "plan": "free",  # free tier
            "region": "oregon",  # or "ohio", "frankfurt"
            "envSpecificDetails": {
                "buildCommand": "npm install && npx prisma generate && npm run build",
                "startCommand": "npx prisma migrate deploy && npm start"
            },
            "envVars": [
                {
                    "key": "NODE_ENV",
                    "value": "production"
                },
                {
                    "key": "ADMIN_PASSWORD",
                    "value": "changeme-admin-2024"
                },
                {
                    "key": "ADMIN_SESSION_SECRET",
                    "value": session_secret
                }
            ]
        }
    }
    
    print("\n🚀 Creating new web service...")
    print(f"   Name: mention-markets-web")
    print(f"   Root Dir: web/")
    print(f"   Plan: free")
    
    response = requests.post(
        f"{BASE_URL}/services",
        headers=get_headers(),
        data=json.dumps(service_config)
    )
    
    if response.ok:
        service = response.json()
        service_id = service.get("service", {}).get("id")
        service_name = service.get("service", {}).get("name")
        
        print(f"\n✅ Service created successfully!")
        print(f"   Service ID: {service_id}")
        print(f"   Name: {service_name}")
        print(f"\n📝 IMPORTANT Next Steps:")
        print(f"   1. Create Postgres database: https://dashboard.render.com/new/database")
        print(f"   2. Add DATABASE_URL env var with the Internal Database URL")
        print(f"   3. Update ADMIN_PASSWORD to something secure")
        print(f"\n⏳ Deploy will start after DATABASE_URL is set...")
        
        return service_id
    else:
        print(f"\n❌ Failed to create service: {response.status_code}")
        print(response.text)
        try:
            error = response.json()
            print(f"\nError: {json.dumps(error, indent=2)}")
        except:
            pass

if __name__ == "__main__":
    create_web_service()
