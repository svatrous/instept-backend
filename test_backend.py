import requests
import json
import sys

def test_analyze_endpoint(url):
    print(f"Testing analysis for URL: {url}")
    endpoint = "http://localhost:8000/analyze"
    
    try:
        response = requests.post(endpoint, json={"url": url})
        
        if response.status_code == 200:
            print("\n✅ Success! Recipe extracted:")
            data = response.json()
            print(json.dumps(data, indent=2))
            return True
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(response.text)
            return False
            
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to backend. Is it running?")
        print("Run: uvicorn main:app --reload")
        return False

if __name__ == "__main__":
    test_url = "https://www.instagram.com/reel/abc12345" # Replace with a real URL or pass as arg
    
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        
    test_analyze_endpoint(test_url)
