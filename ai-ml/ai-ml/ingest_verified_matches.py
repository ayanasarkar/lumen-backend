import os
import json
import argparse
import requests
import rasterio

def format_matches_for_ingest(matches, src_width, src_height, ref_width, ref_height, src_offsets=(0, 0), ref_offsets=(0, 0)):
    """
    Converts local matches into the backend schema.
    Applies column (X) and row (Y) offsets if matching on cropped windows.
    """
    payload = {
        "srcImageWidth": int(src_width),
        "srcImageHeight": int(src_height),
        "refImageWidth": int(ref_width),
        "refImageHeight": int(ref_height),
        "points": []
    }
    
    for m in matches:
        # Pull coordinates supporting both snake_case and camelCase
        src_x = float(m.get("src_x", m.get("srcX", 0.0)))
        src_y = float(m.get("src_y", m.get("srcY", 0.0)))
        ref_x = float(m.get("ref_x", m.get("refX", 0.0)))
        ref_y = float(m.get("ref_y", m.get("refY", 0.0)))
        confidence = float(m.get("confidence", 0.0))
        
        # Apply window offsets to reconstruct full-image coordinates
        full_src_x = src_x + src_offsets[0]
        full_src_y = src_y + src_offsets[1]
        full_ref_x = ref_x + ref_offsets[0]
        full_ref_y = ref_y + ref_offsets[1]
        
        payload["points"].append({
            "srcX": full_src_x,
            "srcY": full_src_y,
            "refX": full_ref_x,
            "refY": full_ref_y,
            "confidence": confidence
        })
        
    return payload

def get_image_dimensions(image_path):
    """Attempts to read image dimensions dynamically; returns None on failure."""
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        with rasterio.open(image_path) as src:
            return src.width, src.height
    except Exception as e:
        print(f"[Warning] Could not read dimensions from {image_path}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="LUMEN Backend Ingestion Utility")
    parser.add_argument("job_id", help="The live job ID in Ayana's database")
    parser.add_argument("json_path", help="Path to your known-good local match JSON (e.g., run_c1515ae3.json)")
    parser.add_argument("backend_url", help="Backend host (e.g., http://localhost:8000 or https://your-domain.com)")
    
    # Optional image path overrides (to read dimensions automatically)
    parser.add_argument("--src-img", help="Path to source image file")
    parser.add_argument("--ref-img", help="Path to reference image file")
    
    # Offsets in case crops were used
    parser.add_argument("--src-offsets", nargs=2, type=float, default=[0.0, 0.0], help="X and Y offset for source crop")
    parser.add_argument("--ref-offsets", nargs=2, type=float, default=[0.0, 0.0], help="X and Y offset for reference crop")
    
    args = parser.parse_args()
    
    # Load the verified local matches
    print(f"Loading local match data from: {args.json_path}")
    try:
        with open(args.json_path, "r") as f:
            local_data = json.load(f)
    except Exception as e:
        print(f"[Error] Failed to load local JSON file: {e}")
        return
        
    # Get match array
    matches = local_data.get("matches", []) if isinstance(local_data, dict) else local_data
    if not matches:
        print("[Error] No match coordinates found in JSON file.")
        return
    print(f"Loaded {len(matches)} match records.")
    
    # Handle dimensions (dynamic with fallback defaults)
    src_w, src_h = 12000, 8000  # standard OHRC template
    ref_w, ref_h = 1000, 1000   # standard crop template
    
    src_dims = get_image_dimensions(args.src_img)
    if src_dims:
        src_w, src_h = src_dims
        print(f"Read Source Image dimensions dynamically: {src_w}x{src_h}")
        
    ref_dims = get_image_dimensions(args.ref_img)
    if ref_dims:
        ref_w, ref_h = ref_dims
        print(f"Read Reference Image dimensions dynamically: {ref_w}x{ref_h}")
        
    # Build payload
    payload = format_matches_for_ingest(
        matches=matches,
        src_width=src_w,
        src_height=src_h,
        ref_width=ref_w,
        ref_height=ref_h,
        src_offsets=args.src_offsets,
        ref_offsets=args.ref_offsets
    )
    
    # Construct ingestion endpoint
    base_url = args.backend_url.rstrip("/")
    target_url = f"{base_url}/api/v1/jobs/{args.job_id}/matches/ingest"
    
    print(f"Prepared Payload: points={len(payload['points'])}, src_dims={src_w}x{src_h}, ref_dims={ref_w}x{ref_h}")
    if payload['points']:
        print(f"First mapped point output: {payload['points'][0]}")
        
    # Confirm run
    confirm = input("\nProceed with POST request? (y/n): ")
    if confirm.lower() != 'y':
        print("Canceled.")
        return
        
    print(f"\nSending POST to {target_url}...")
    try:
        response = requests.post(target_url, json=payload, timeout=30)
        print(f"[Ingest] Status Code: {response.status_code}")
        print(f"[Ingest] Response Body: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"[Ingest Failed] Connection error: {e}")

if __name__ == "__main__":
    main()