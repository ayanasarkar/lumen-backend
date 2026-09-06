import sys
import rasterio

def verify_file(file_path):
    print(f"--- Verifying File: {file_path} ---")
    try:
        with rasterio.open(file_path) as src:
            crs = src.crs
            transform = src.transform
            
            print(f"Width     : {src.width}")
            print(f"Height    : {src.height}")
            print(f"Dtype     : {src.dtypes[0]}")
            print(f"CRS       : {crs}")
            print(f"Transform : {transform}")
            
            # Check if CRS exists and transform is NOT the default identity matrix
            if crs is not None and not transform.is_identity:
                print("\n[PASS] Real CRS and non-identity transform are present.")
            else:
                print("\n[FAIL] Dataset lacks proper georeferencing (No CRS or Identity transform).")
                
    except Exception as e:
        print(f"\n[FAIL] Error reading file with rasterio: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_georeferencing.py <path_to_real_geotiff>")
        sys.exit(1)
        
    verify_file(sys.argv[1])