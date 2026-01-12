import os
import requests

N8N_ENDPOINT = os.environ.get("N8N_ENDPOINT") or 'http://localhost:5678/webhook/7702ef4c-9803-4070-a2bb-437fa4c5ac82'

def trigger(action: str, folder_name: str):
    """
    Trigger an N8N workflow.
    
    Args:
        action: The action to perform. Currently only 'analyze' is supported.
        folder_name: The folder name to send in the payload.
    """
    if action == 'analyze':
        payload = {'folder': folder_name}
        
        print(f"Triggering N8N analyze for folder: {folder_name}...")
        try:
            response = requests.post(N8N_ENDPOINT, json=payload)
            response.raise_for_status()
            print(f"Success: N8N triggered. Status Code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error triggering N8N: {e}")
    else:
        print(f"Action '{action}' is not supported.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="N8N Trigger CLI")
    parser.add_argument("action", choices=["analyze"], help="Action to perform")
    parser.add_argument("folder_name", help="Folder name parameter for the action")
    
    args = parser.parse_args()
    
    trigger(args.action, args.folder_name)
